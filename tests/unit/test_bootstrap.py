"""Bootstrap tests: CLI smoke, help, stub behavior, and package version."""

import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class CliBootstrapTests(unittest.TestCase):
    def _run(self, argv: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "opsledger", *argv],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_cli_diagnostics_smoke(self):
        proc = self._run(["diagnostics"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["package"], "opsledger")
        self.assertEqual(payload["version"], "0.1.0")
        self.assertTrue(payload["python"].startswith("3."))

    def test_cli_help(self):
        proc = self._run(["--help"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("migrate", proc.stdout)
        self.assertIn("diagnostics", proc.stdout)

    def test_cli_stub_returns_2(self):
        proc = self._run(["migrate"])
        self.assertEqual(proc.returncode, 2)
        self.assertIn("not implemented", proc.stderr)

    def test_package_version(self):
        sys.path.insert(0, str(ROOT))
        try:
            import opsledger

            self.assertEqual(opsledger.__version__, "0.1.0")
        finally:
            sys.path.pop(0)


if __name__ == "__main__":
    unittest.main()
