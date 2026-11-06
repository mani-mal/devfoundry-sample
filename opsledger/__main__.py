"""Command line entry point for OpsLedger (bootstrap)."""

import argparse
import json
import platform
import sys

from . import __version__

STUB_COMMANDS = ("migrate", "serve", "seed", "reconcile", "backup", "restore")


def _run_stub(_ns: argparse.Namespace) -> int:
    print("not implemented in bootstrap", file=sys.stderr)
    return 2


def _run_diagnostics(_ns: argparse.Namespace) -> int:
    payload = {
        "package": "opsledger",
        "version": __version__,
        "python": platform.python_version(),
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="opsledger",
        description="OpsLedger command line interface (bootstrap).",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in STUB_COMMANDS:
        stub = subparsers.add_parser(
            name, help=f"{name} (not implemented in bootstrap)"
        )
        stub.set_defaults(handler=_run_stub)

    diagnostics = subparsers.add_parser(
        "diagnostics", help="print bootstrap diagnostics JSON"
    )
    diagnostics.set_defaults(handler=_run_diagnostics)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    ns = parser.parse_args(argv)
    return ns.handler(ns)


if __name__ == "__main__":
    raise SystemExit(main())
