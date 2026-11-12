"""Tests for the HTTP foundation: router and JSON error envelope (T005).

Runs a real ephemeral-bound server (127.0.0.1, port 0) and exercises the
transport classes end to end with urllib.
"""

import json
import threading
import unittest
import urllib.error
import urllib.request

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from opsledger.http import (  # noqa: E402
    Router,
    RouterServer,
)
from opsledger.core.errors import ValidationError  # noqa: E402


def _read_error(exc: urllib.error.HTTPError) -> dict:
    body = exc.read()
    return json.loads(body.decode("utf-8"))


class HttpFoundationTests(unittest.TestCase):
    def setUp(self):
        self._servers = []

    def tearDown(self):
        for server, thread in self._servers:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def _start(self, router):
        router.add("/api/v1/healthz", "GET", lambda request: (200, {"status": "ok"}))
        server = RouterServer(router, host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._servers.append((server, thread))
        return f"http://127.0.0.1:{server.server_address[1]}"

    def test_unknown_route_returns_404_envelope(self):
        base = self._start(Router())
        try:
            urllib.request.urlopen(base + "/api/v1/nope", timeout=5)
            self.fail("expected HTTPError")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 404)
            payload = _read_error(exc)
        self.assertEqual(payload["error"]["code"], "not_found")
        self.assertTrue(payload["error"]["request_id"])

    def test_disallowed_method_returns_405_envelope_with_allow(self):
        router = Router()
        base = self._start(router)
        try:
            req = urllib.request.Request(
                base + "/api/v1/healthz", method="DELETE"
            )
            urllib.request.urlopen(req, timeout=5)
            self.fail("expected HTTPError")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 405)
            payload = _read_error(exc)
            allow = exc.headers.get("Allow")
        self.assertEqual(allow, "GET")
        self.assertEqual(payload["error"]["code"], "method_not_allowed")
        self.assertTrue(payload["error"]["request_id"])

    def _post(self, base: str, path: str, *, data: bytes, content_type: str):
        request = urllib.request.Request(
            base + path,
            data=data,
            headers={"Content-Type": content_type},
            method="POST",
        )
        return urllib.request.urlopen(request, timeout=5)

    def test_malformed_json_returns_400_envelope(self):
        router = Router()
        router.add("/api/v1/echo", "POST", lambda request: (200, {"received": True}))
        base = self._start(router)
        try:
            self._post(base, "/api/v1/echo", data=b"{not json", content_type="application/json")
            self.fail("expected HTTPError")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 400)
            payload = _read_error(exc)
        self.assertEqual(payload["error"]["code"], "malformed_json")
        self.assertTrue(payload["error"]["request_id"])

    def test_oversized_body_returns_413_envelope(self):
        router = Router(body_limit_bytes=64)
        router.add("/api/v1/echo", "POST", lambda request: (200, {"received": True}))
        base = self._start(router)
        try:
            self._post(base, "/api/v1/echo", data=b"x" * 65, content_type="application/json")
            self.fail("expected HTTPError")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 413)
            payload = _read_error(exc)
        self.assertEqual(payload["error"]["code"], "body_too_large")
        self.assertTrue(payload["error"]["request_id"])

    def test_wrong_content_type_returns_415_envelope(self):
        router = Router()
        router.add("/api/v1/echo", "POST", lambda request: (200, {"received": True}))
        base = self._start(router)
        try:
            self._post(base, "/api/v1/echo", data=b"plain text", content_type="text/plain")
            self.fail("expected HTTPError")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 415)
            payload = _read_error(exc)
        self.assertEqual(payload["error"]["code"], "unsupported_media_type")
        self.assertTrue(payload["error"]["request_id"])

    def test_validation_error_returns_422_envelope_with_request_id(self):
        def raise_validation(request):
            raise ValidationError("name is required")

        router = Router()
        router.add("/api/v1/boom", "POST", raise_validation)
        base = self._start(router)
        try:
            self._post(base, "/api/v1/boom", data=b"{}", content_type="application/json")
            self.fail("expected HTTPError")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 422)
            payload = _read_error(exc)
        self.assertEqual(payload["error"]["code"], "validation_error")
        self.assertEqual(payload["error"]["message"], "name is required")
        self.assertTrue(payload["error"]["request_id"])
        self.assertNotIn("Traceback", json.dumps(payload))

    def test_unexpected_exception_returns_500_envelope_no_traceback(self):
        def raise_runtime(request):
            raise RuntimeError("secret internal detail")

        router = Router()
        router.add("/api/v1/crash", "POST", raise_runtime)
        base = self._start(router)
        try:
            self._post(base, "/api/v1/crash", data=b"{}", content_type="application/json")
            self.fail("expected HTTPError")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 500)
            payload = _read_error(exc)
        self.assertEqual(payload["error"]["code"], "internal_error")
        self.assertEqual(payload["error"]["message"], "internal server error")
        self.assertTrue(payload["error"]["request_id"])
        body_text = json.dumps(payload)
        self.assertNotIn("Traceback", body_text)
        self.assertNotIn("RuntimeError", body_text)
        self.assertNotIn("secret", body_text)

    def test_clean_healthz_returns_200_ok(self):
        base = self._start(Router())
        with urllib.request.urlopen(base + "/api/v1/healthz", timeout=5) as response:
            self.assertEqual(response.status, 200)
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload, {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
