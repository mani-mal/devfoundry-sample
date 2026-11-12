"""Tests for the application CLI and diagnostics handlers (T006).

Exercises the argparse subcommands (migrate, serve rules) and the two
HTTP endpoints end to end with a real ephemeral-bound server
(127.0.0.1, port 0) and urllib.
"""

import contextlib
import io
import json
import pathlib
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from opsledger.cli import main as cli_main  # noqa: E402
from opsledger.core.errors import ConflictError  # noqa: E402
from opsledger.http import RouterServer  # noqa: E402
from opsledger.http.handlers import (  # noqa: E402
    configure_readyz,
    readyz_handler,
)


def _run_cli(argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = cli_main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


@contextlib.contextmanager
def socket_context_free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        name = sock.getsockname()
    finally:
        sock.close()
    yield name


def _read_error(exc: urllib.error.HTTPError) -> dict:
    body = exc.read()
    return json.loads(body.decode("utf-8"))


class CliMigrateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = pathlib.Path(self._tmp.name)
        self.db_path = self.tmp_path / "db.sqlite"
        configure_readyz(None)
        self.addCleanup(lambda: configure_readyz(None))

    def test_migrate_on_fresh_temp_database_exits_0_printing_applied_ids(self):
        code, out, err = _run_cli(["migrate", str(self.db_path)])

        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ["0001_initial", "0002_identity", "0003_sessions"])
        self.assertEqual(err, "")

    def test_second_migrate_exits_0_and_prints_nothing(self):
        self.assertEqual(_run_cli(["migrate", str(self.db_path)])[0], 0)

        code, out, err = _run_cli(["migrate", str(self.db_path)])

        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertEqual(err, "")

    def test_edited_applied_file_exits_1_with_public_message_no_traceback(self):
        migrations_dir = self.tmp_path / "migrations"
        migrations_dir.mkdir()
        (migrations_dir / "0001_initial.sql").write_text(
            pathlib.Path(ROOT / "opsledger" / "migrations" / "0001_initial.sql")
            .read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (migrations_dir / "0002_identity.sql").write_text(
            "CREATE TABLE altered (id INTEGER PRIMARY KEY)",
            encoding="utf-8",
        )
        self.assertEqual(
            _run_cli(["migrate", str(self.db_path), "--migrations", str(migrations_dir)])[0],
            0,
        )
        (migrations_dir / "0002_identity.sql").write_text(
            "CREATE TABLE altered (id INTEGER PRIMARY KEY, extra TEXT)",
            encoding="utf-8",
        )

        code, out, err = _run_cli(["migrate", str(self.db_path), "--migrations", str(migrations_dir)])

        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("applied migration content changed", err)
        self.assertIn("0002_identity", err)
        self.assertNotIn("Traceback", err)
        self.assertNotIn(".sql", err)
        self.assertNotIn(str(migrations_dir), err)


class ReadyzHandlerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = pathlib.Path(self.tmp_dir())
        self.db_path = self.tmp_path / "db.sqlite"
        configure_readyz(None)
        self.addCleanup(lambda: configure_readyz(None))

    def tmp_dir(self):
        return self._tmp.name

    def _request(self):
        return object()

    def test_readyz_on_un_migrated_database_is_503_unready(self):
        configure_readyz(str(self.db_path))

        status, body = readyz_handler(self._request())

        self.assertEqual(status, 503)
        self.assertEqual(body["error"]["code"], "unready")
        self.assertEqual(body["error"]["message"], "the schema has not been migrated")
        self.assertTrue(body["error"]["request_id"])

    def test_readyz_without_configuration_is_503_unready(self):
        status, body = readyz_handler(self._request())

        self.assertEqual(status, 503)
        self.assertEqual(body["error"]["code"], "unready")

    def test_readyz_after_migrate_is_200_ready_with_count(self):
        self.assertEqual(_run_cli(["migrate", str(self.db_path)])[0], 0)
        configure_readyz(str(self.db_path))

        status, body = readyz_handler(self._request())

        self.assertEqual(status, 200)
        self.assertEqual(body, {"status": "ready", "migrations": 3})

    def test_readyz_with_missing_history_row_is_503_naming_it(self):
        self.assertEqual(_run_cli(["migrate", str(self.db_path)])[0], 0)
        configure_readyz(str(self.db_path))
        conn = sys.modules["opsledger.core.db"].connect(str(self.db_path))
        try:
            conn.execute("DELETE FROM schema_migrations WHERE migration_id = '0002_identity'")
            conn.commit()
        finally:
            conn.close()

        status, body = readyz_handler(self._request())

        self.assertEqual(status, 503)
        self.assertEqual(body["error"]["code"], "unready")
        self.assertIn("0002_identity", body["error"]["message"])

    def test_readyz_bodies_never_contain_a_path_or_traceback(self):
        configure_readyz(str(self.db_path))
        bodies = []

        status_before, body_before = readyz_handler(self._request())
        bodies.append((status_before, body_before))

        self.assertEqual(_run_cli(["migrate", str(self.db_path)])[0], 0)
        status_ready, body_ready = readyz_handler(self._request())
        bodies.append((status_ready, body_ready))

        import sys as _sys

        db_module = _sys.modules["opsledger.core.db"]
        conn = db_module.connect(str(self.db_path))
        try:
            conn.execute("DELETE FROM schema_migrations WHERE migration_id = '0002_identity'")
            conn.commit()
        finally:
            conn.close()
        status_missing, body_missing = readyz_handler(self._request())
        bodies.append((status_missing, body_missing))

        serialized = [json.dumps(body) for _, body in bodies]
        for text in serialized:
            self.assertNotIn(str(self.tmp_path), text)
            self.assertNotIn("workspace", text)
            self.assertNotIn("Traceback", text)
        self.assertEqual(bodies[0][0], 503)
        self.assertEqual(bodies[1][0], 200)
        self.assertEqual(bodies[2][0], 503)


class HealthzEndToEndTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._servers = []
        configure_readyz(None)
        self.addCleanup(lambda: configure_readyz(None))

    def tearDown(self):
        for server, thread in self._servers:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def _start(self):
        from opsledger.http.handlers import build_router

        router = build_router()
        server = RouterServer(router, host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._servers.append((server, thread))
        return f"http://127.0.0.1:{server.server_address[1]}"

    def test_healthz_end_to_end_returns_200_ok(self):
        base = self._start()

        with urllib.request.urlopen(base + "/api/v1/healthz", timeout=5) as response:
            self.assertEqual(response.status, 200)
            payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual(payload, {"status": "ok"})

    def test_readyz_end_to_end_is_503_when_nothing_migrated(self):
        base = self._start()

        try:
            urllib.request.urlopen(base + "/api/v1/readyz", timeout=5)
            self.fail("expected HTTPError")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 503)
            payload = _read_error(exc)

        self.assertEqual(payload["error"]["code"], "unready")

    def test_readyz_end_to_end_after_migrate_is_200_ready(self):
        db_path = pathlib.Path(self._tmp.name) / "db.sqlite"
        self.assertEqual(_run_cli(["migrate", str(db_path)])[0], 0)
        configure_readyz(str(db_path))
        base = self._start()

        with urllib.request.urlopen(base + "/api/v1/readyz", timeout=5) as response:
            self.assertEqual(response.status, 200)
            payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual(payload, {"status": "ready", "migrations": 3})


class ServeShutdownRulesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        configure_readyz(None)
        self.addCleanup(lambda: configure_readyz(None))

    def test_cli_module_documents_signal_shutdown_pattern(self):
        source = pathlib.Path(ROOT / "opsledger" / "cli.py").read_text(encoding="utf-8")
        self.assertIn("server.shutdown()", source)
        self.assertIn("server.server_close()", source)

    def test_serve_end_to_end_shutdown_exits_cleanly(self):
        db_path = pathlib.Path(self._tmp.name) / "db.sqlite"
        self.assertEqual(_run_cli(["migrate", str(db_path)])[0], 0)
        configure_readyz(None)

        with socket_context_free_port() as (host, port):
            proc = subprocess.Popen(
                [
                    sys.executable, "-m", "opsledger.cli", "serve", str(db_path),
                    "--host", host, "--port", str(port),
                ],
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                base = f"http://{host}:{port}"
                deadline = time.monotonic() + 10
                while True:
                    if proc.poll() is not None:
                        self.fail("serve process exited before shutdown")
                    try:
                        with urllib.request.urlopen(base + "/api/v1/healthz", timeout=1) as response:
                            self.assertEqual(response.status, 200)
                            self.assertEqual(
                                json.loads(response.read().decode("utf-8")),
                                {"status": "ok"},
                            )
                        break
                    except urllib.error.URLError:
                        if time.monotonic() > deadline:
                            self.fail("serve process did not become ready")
                        time.sleep(0.1)
                proc.send_signal(signal.SIGINT)
                code = proc.wait(timeout=10)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=5)
                if proc.stdout is not None:
                    proc.stdout.close()
                if proc.stderr is not None:
                    proc.stderr.close()
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
