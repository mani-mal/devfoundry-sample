#!/usr/bin/env python3.12
"""Tmp-clean wrapper: fail when a command run leaves new temp artifacts in /tmp.

Independent of check.sh (never edits it). Usage:

    python3.12 scripts/check_tmp_clean.py <label> <command> [args...]

Snapshots /tmp's temp artifacts before the command (``tmp*`` files and
``upgrade-fixture-*`` / ``fresh-checkout-*`` directories), runs the
command, then re-snapshots. New artifacts that still exist after the
command fail the wrapper with a listing and exit 1; otherwise the
command's own exit code is returned.
"""

import os
import subprocess
import sys


def snapshot(tmp: str) -> set[str]:
    try:
        return set(os.listdir(tmp))
    except FileNotFoundError:
        return set()


def artifacts(entries: set[str]) -> set[str]:
    prefixes = ("tmp", "upgrade-fixture-", "fresh-checkout-")
    return {e for e in entries if e.startswith(prefixes)}


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: check_tmp_clean.py <label> <command> [args...]", file=sys.stderr)
        return 2
    label, cmd = argv[1], argv[2:]
    before = artifacts(snapshot("/tmp"))
    proc = subprocess.run(cmd, cwd=os.getcwd())
    leftover = artifacts(snapshot("/tmp")) - before
    if leftover:
        print(f"TMP_NOT_CLEAN [{label}]: {len(leftover)} artifact(s) left in /tmp:")
        for name in sorted(leftover)[:10]:
            print(f"  {name}")
        if len(leftover) > 10:
            print(f"  ... and {len(leftover) - 10} more")
        return 1
    print(f"TMP_CLEAN [{label}] (no new temp artifacts)")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
