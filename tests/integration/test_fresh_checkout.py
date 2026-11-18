"""Integration tests (T072, part 1 of 2): fresh-checkout startability.

Copies the repository (without ``.git``, ``__pycache__``, ``*.pyc`` and
``web/``) into a temporary directory and verifies, with subprocesses only,
that a fresh copy still runs the REAL shipped commands via
``python -m opsledger.cli``: ``migrate`` applies exactly 24 migrations and
``serve`` becomes healthy on loopback and exits cleanly on SIGINT — with
no package installation. Also checks the CLI entry points (--help) and the
bootstrap stub contract. Real commands live in ``opsledger.cli``; the
``python -m opsledger`` bootstrap only exposes diagnostics and stubs.
"""

import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


class FreshCheckoutTests(unittest.TestCase):
    def _fresh_copy(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        copy = shutil.copytree(
            ROOT,
            pathlib.Path(tmp.name) / "checkout",
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", "web"),
        )
        return pathlib.Path(copy)

    def _free_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        return port

    def test_fresh_copy_migrates_and_serves_without_installation(self):
        copy = self._fresh_copy()
        db = "fresh.db"
        result = subprocess.run(
            [sys.executable, "-m", "opsledger.cli", "migrate", db],
            cwd=copy,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0)
        printed = [line for line in result.stdout.splitlines() if line.strip()]
        self.assertEqual(len(printed), 24)

        port = self._free_port()
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "opsledger.cli",
                "serve",
                db,
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=copy,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            deadline = time.monotonic() + 10
            status = None
            while time.monotonic() < deadline:
                try:
                    with urllib.request.urlopen(
                        "http://127.0.0.1:%d/api/v1/healthz" % port, timeout=1
                    ) as response:
                        status = response.status
                    break
                except (ConnectionError, OSError):
                    time.sleep(0.1)
            self.assertEqual(status, 200)
            proc.send_signal(signal.SIGINT)
            self.assertEqual(proc.wait(timeout=10), 0)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10)
            for pipe in (proc.stdout, proc.stderr):
                if pipe is not None:
                    pipe.close()

    def test_fresh_copy_cli_entry_points_help(self):
        copy = self._fresh_copy()
        for argv in (
            [sys.executable, "-m", "opsledger", "--help"],
            [sys.executable, "-m", "opsledger.cli", "--help"],
            [sys.executable, "-m", "opsledger.reconcile_cli", "--help"],
        ):
            result = subprocess.run(
                argv, cwd=copy, capture_output=True, text=True, timeout=60
            )
            self.assertEqual(result.returncode, 0)
        stub = subprocess.run(
            [sys.executable, "-m", "opsledger", "migrate"],
            cwd=copy,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(stub.returncode, 2)
        self.assertIn("not implemented", stub.stderr)


if __name__ == "__main__":
    unittest.main()
