#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONHASHSEED=0
export TZ=UTC
python3 - <<'PY'
from pathlib import Path
import subprocess
import sys
import unittest

root = Path.cwd()
if sys.version_info[:2] != (3, 12):
    raise SystemExit("Python 3.12 required by qualified baseline")

sources = sorted((root / "opsledger").rglob("*.py"))
if not sources:
    raise SystemExit("No application Python source files")
for path in sources:
    compile(path.read_text(encoding="utf-8"), str(path), "exec")

suite = unittest.defaultTestLoader.discover(
    start_dir=str(root / "tests"), pattern="test_*.py", top_level_dir=str(root)
)
if suite.countTestCases() == 0:
    raise SystemExit("No Python tests discovered")
result = unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful():
    raise SystemExit(1)
if result.skipped or result.expectedFailures or result.unexpectedSuccesses:
    raise SystemExit("Skipped/expected-failure tests are not allowed in the fast gate")

node = subprocess.run(
    ["node", "-p", "process.versions.node.split('.')[0]"],
    check=True, capture_output=True, text=True, timeout=10
).stdout.strip()
if node != "22":
    raise SystemExit("Node 22 required by qualified baseline")
for path in sorted((root / "web").rglob("*.mjs")):
    subprocess.run(["node", "--check", str(path)], check=True, timeout=10)
js_tests = sorted((root / "tests" / "js").rglob("*.test.mjs"))
if not js_tests:
    raise SystemExit("No JavaScript test files discovered")
subprocess.run(
    ["node", "--test", *map(str, js_tests)], check=True, timeout=60
)
print("OPSLEDGER_FAST_GATE_OK")
PY
