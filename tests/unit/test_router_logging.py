"""Tests for router logging correlation (T066): request ids shared with logs.

Runs a real ephemeral-bound server (127.0.0.1, port 0) and checks that the
request id in error envelopes matches the id written to the log stream.
"""

import io
import json
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from opsledger.http import (  # noqa: E402
    Router,
    RouterServer,
)
from opsledger.http.jsonlog import JsonLogger  # noqa: E402
from opsledger.core.clock import FixedClock  # noqa: E402


def _read_error(exc: urllib.error.HTTPError) -> dict:
    body = exc.read()
    return json.loads(body.decode("utf-8"))


def _read_lines(buffer: str) -> list[dict]:
    return [json.loads(line) for line in buffer.splitlines() if line]


class RouterLoggingTests(unittest.TestCase):
    def setUp(self):
        self._servers = []
        self._streams = []

    def tearDown(self):
        for server, thread in self._servers:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def _logger(self) -> JsonLogger:
        stream = io.StringIO()
        self._streams.append(stream)
        return JsonLogger(stream=stream)

    def _start(self, router):
        router.add("/api/v1/healthz", "GET", lambda request: (200, {"status": "ok"}))
        server = RouterServer(router, host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._servers.append((server, thread))
        return f"http://127.0.0.1:{server.server_address[1]}"

    def test_router_without_logger_stays_silent(self):
        base = self._start(Router())
        with urllib.request.urlopen(base + "/api/v1/healthz", timeout=5) as response:
            self.assertEqual(response.status, 200)

    def test_success_requests_are_logged_with_request_id(self):
        clock = FixedClock(datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc))
        router = Router(logger=self._logger(), clock=clock)
        base = self._start(router)
        with urllib.request.urlopen(base + "/api/v1/healthz", timeout=5) as response:
            self.assertEqual(response.status, 200)
        records = _read_lines(self._streams[0].getvalue())
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["event"], "request")
        self.assertEqual(record["method"], "GET")
        self.assertEqual(record["path"], "/api/v1/healthz")
        self.assertEqual(record["status"], 200)
        self.assertEqual(record["ts"], "2026-11-18T12:00:00Z")
        self.assertTrue(isinstance(record["request_id"], str))
        self.assertTrue(record["request_id"])

    def test_error_envelope_reuses_the_logged_request_id(self):
        clock = FixedClock(datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc))
        router = Router(logger=self._logger(), clock=clock)
        base = self._start(router)
        try:
            urllib.request.urlopen(base + "/api/v1/nope", timeout=5)
            self.fail("expected HTTPError")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 404)
            payload = _read_error(exc)
        records = _read_lines(self._streams[0].getvalue())
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(payload["error"]["request_id"], record["request_id"])
        self.assertEqual(record["status"], 404)

    def test_logging_failure_never_breaks_the_response(self):
        class BrokenLogger:
            def log_request(self, *args, **kwargs):
                raise RuntimeError("boom")

        router = Router(logger=BrokenLogger())
        base = self._start(router)
        with urllib.request.urlopen(base + "/api/v1/healthz", timeout=5) as response:
            self.assertEqual(response.status, 200)
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload, {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
