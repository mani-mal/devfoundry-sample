"""T070 shutdown drain tests: the bounded drain before server_close.

Exercises ``RouterServer.drain(timeout)`` end to end: shutdown abandons no
in-flight handler (the drain waits for it), the drain wait is bounded by its
timeout, an in-flight write drains before close leaving the database intact,
and the serve process exits 0 on SIGINT/SIGTERM.
"""

import contextlib
import pathlib
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from opsledger.core.db import connect, transaction  # noqa: E402
from opsledger.core.migrations import migrate  # noqa: E402
from opsledger.http import Router, RouterServer  # noqa: E402


@contextlib.contextmanager
def socket_context_free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        name = sock.getsockname()
    finally:
        sock.close()
    yield name


class ShutdownDrainTests(unittest.TestCase):
    def test_in_flight_request_is_drained_before_close(self):
        started = threading.Event()

        def slow_handler(request):
            started.set()
            time.sleep(1.0)
            return (200, {"status": "slow"})

        router = Router()
        router.add("/api/v1/slow", "GET", slow_handler)
        server = RouterServer(router, host="127.0.0.1", port=0)
        serve_thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True
        )
        serve_thread.start()
        result = {}

        def client():
            with urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_address[1]}/api/v1/slow",
                timeout=10,
            ) as response:
                result["status"] = response.status

        client_thread = threading.Thread(target=client, daemon=True)
        client_thread.start()
        self.assertTrue(started.wait(timeout=5), "handler did not start")

        drain_started_at = time.monotonic()
        server.shutdown()
        pending = server.drain(timeout=5.0)
        server.server_close()
        drain_elapsed = time.monotonic() - drain_started_at

        client_thread.join(timeout=10)
        self.assertFalse(client_thread.is_alive(), "client thread still running")
        self.assertEqual(pending, 0)
        self.assertEqual(result["status"], 200)
        self.assertGreaterEqual(drain_elapsed, 0.4)

    def test_drain_timeout_is_bounded(self):
        started = threading.Event()
        released = threading.Event()

        def blocked_handler(request):
            started.set()
            released.wait(timeout=30)
            return (200, {"status": "blocked"})

        router = Router()
        router.add("/api/v1/blocked", "GET", blocked_handler)
        server = RouterServer(router, host="127.0.0.1", port=0)
        serve_thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True
        )
        serve_thread.start()

        def client():
            try:
                urllib.request.urlopen(
                    f"http://127.0.0.1:{server.server_address[1]}/api/v1/blocked",
                    timeout=60,
                )
            except Exception:
                pass

        client_thread = threading.Thread(target=client, daemon=True)
        client_thread.start()
        self.assertTrue(started.wait(timeout=5), "handler did not start")

        drain_started_at = time.monotonic()
        pending = server.drain(timeout=1.0)
        drain_elapsed = time.monotonic() - drain_started_at

        shutdown_started_at = time.monotonic()
        server.shutdown()
        shutdown_elapsed = time.monotonic() - shutdown_started_at

        close_started_at = time.monotonic()
        server.server_close()
        close_elapsed = time.monotonic() - close_started_at

        released.set()
        self.assertGreaterEqual(pending, 1)
        self.assertLess(drain_elapsed, 3.0)
        self.assertLess(shutdown_elapsed, 3.0)
        self.assertLess(close_elapsed, 3.0)

    def test_shutdown_mid_write_leaves_database_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = pathlib.Path(tmp) / "db.sqlite"
            setup_conn = connect(str(db_path))
            self.addCleanup(setup_conn.close)
            migrate(setup_conn, "opsledger/migrations")
            setup_conn.close()

            started = threading.Event()

            def writing_handler(request):
                handler_conn = connect(str(db_path))
                try:
                    with transaction(handler_conn) as tx:
                        tx.execute(
                            "INSERT INTO organizations (id, slug, name, created_at)"
                            " VALUES ('org-drain-0001', 'drain-check', 'Drain Check',"
                            " '2026-11-18T12:00:00Z')"
                        )
                        started.set()
                        time.sleep(1.0)
                finally:
                    handler_conn.close()
                return (200, {"status": "written"})

            router = Router()
            router.add("/api/v1/write", "GET", writing_handler)
            server = RouterServer(router, host="127.0.0.1", port=0)
            serve_thread = threading.Thread(
                target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True
            )
            serve_thread.start()
            result = {}

            def client():
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{server.server_address[1]}/api/v1/write",
                    timeout=10,
                ) as response:
                    result["status"] = response.status

            client_thread = threading.Thread(target=client, daemon=True)
            client_thread.start()
            self.assertTrue(started.wait(timeout=5), "handler did not start")

            server.shutdown()
            pending = server.drain(timeout=5.0)
            server.server_close()

            client_thread.join(timeout=10)
            self.assertFalse(client_thread.is_alive(), "client thread still running")
            self.assertEqual(pending, 0)
            self.assertEqual(result["status"], 200)

            verify_conn = connect(str(db_path))
            self.addCleanup(verify_conn.close)
            row = verify_conn.execute(
                "SELECT slug, name, created_at FROM organizations"
                " WHERE id = 'org-drain-0001'"
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(
                (row["slug"], row["name"], row["created_at"]),
                ("drain-check", "Drain Check", "2026-11-18T12:00:00Z"),
            )
            self.assertEqual(
                verify_conn.execute("PRAGMA integrity_check").fetchone()[0],
                "ok",
            )
            self.assertEqual(
                verify_conn.execute("PRAGMA foreign_key_check").fetchall(),
                [],
            )

    def test_cli_serve_exits_0_on_sigint_and_sigterm(self):
        for sig in (signal.SIGINT, signal.SIGTERM):
            with tempfile.TemporaryDirectory() as tmp:
                db_path = pathlib.Path(tmp) / "db.sqlite"
                with socket_context_free_port() as (host, port):
                    proc = subprocess.Popen(
                        [
                            sys.executable, "-m", "opsledger.cli", "serve",
                            str(db_path), "--host", host, "--port", str(port),
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
                                with urllib.request.urlopen(
                                    base + "/api/v1/healthz", timeout=1
                                ) as response:
                                    self.assertEqual(response.status, 200)
                                break
                            except Exception:
                                if time.monotonic() > deadline:
                                    self.fail("serve process did not become ready")
                                time.sleep(0.1)
                        proc.send_signal(sig)
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
