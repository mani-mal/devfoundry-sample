"""Application CLI for OpsLedger: migrate and serve (T006).

Stdlib argparse only. Runnable via ``python -m opsledger.cli``.

- ``migrate DATABASE [--migrations DIR]``: connect with
  :func:`opsledger.core.db.connect`, run
  :func:`opsledger.core.migrations.migrate`, print each applied
  ``migration_id`` one per line, exit 0. On :class:`ConflictError` /
  :class:`ValidationError` the public message is printed to stderr and the
  process exits 1 — never a traceback.
- ``serve DATABASE [--host H] [--port P]`` (defaults 127.0.0.1 / 8080):
  run migrations first (same rules), build the diagnostics router
  (:func:`opsledger.http.handlers.build_router`), and serve with
  :class:`RouterServer` until SIGINT/SIGTERM. Shutdown is ``shutdown()`` +
  ``server_close()`` and a clean exit 0.

Failures surface only public messages: no tracebacks and no paths (neither
the database path nor the migrations directory) are printed.
"""

from __future__ import annotations

import argparse
import signal
import sys

from opsledger.core.db import connect
from opsledger.core.errors import ApplicationError
from opsledger.core.migrations import migrate

__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_MIGRATIONS_DIR",
    "DEFAULT_PORT",
    "main",
]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
DEFAULT_MIGRATIONS_DIR = "opsledger/migrations"

_SIGNAL_SHUTDOWN_TIMEOUT_SECONDS = 5


def _run_migrations(database: str, migrations_dir: str) -> list[str]:
    """Apply pending migrations from ``migrations_dir`` to ``database``.

    Returns the applied ``migration_id`` values in application order.
    Application errors and sqlite3 errors propagate to the caller.
    """
    conn = connect(database)
    try:
        return migrate(conn, migrations_dir)
    finally:
        conn.close()


def _cmd_migrate(ns: argparse.Namespace) -> int:
    try:
        applied = _run_migrations(ns.database, ns.migrations)
    except ApplicationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for migration_id in applied:
        print(migration_id)
    return 0


def _cmd_serve(ns: argparse.Namespace) -> int:
    from opsledger.http.handlers import configure_readyz
    from opsledger.http.router import RouterServer

    try:
        _run_migrations(ns.database, ns.migrations)
    except ApplicationError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    configure_readyz(ns.database)
    server = RouterServer(router=_build_router(), host=ns.host, port=ns.port)

    interrupted = False

    def _handle_signal(signum, frame):  # noqa: A002
        nonlocal interrupted
        interrupted = True
        raise KeyboardInterrupt()

    previous_int = signal.signal(signal.SIGINT, _handle_signal)
    previous_term = signal.signal(signal.SIGTERM, _handle_signal)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGINT, previous_int)
        signal.signal(signal.SIGTERM, previous_term)

    server.shutdown()
    server.server_close()
    return 0


def _build_router():
    from opsledger.http.handlers import build_router

    return build_router()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="opsledger",
        description="OpsLedger application CLI (migrate, serve).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    migrate_parser = subparsers.add_parser(
        "migrate", help="apply pending SQL migrations to the database"
    )
    migrate_parser.add_argument("database", help="path to the SQLite database file")
    migrate_parser.add_argument(
        "--migrations",
        default=DEFAULT_MIGRATIONS_DIR,
        help="directory of numbered SQL migrations"
        f" (default: {DEFAULT_MIGRATIONS_DIR})",
    )
    migrate_parser.set_defaults(handler=_cmd_migrate)

    serve_parser = subparsers.add_parser(
        "serve", help="run migrations and serve the diagnostics HTTP endpoints"
    )
    serve_parser.add_argument("database", help="path to the SQLite database file")
    serve_parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"interface to bind (default: {DEFAULT_HOST})",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"port to bind (default: {DEFAULT_PORT})",
    )
    serve_parser.add_argument(
        "--migrations",
        default=DEFAULT_MIGRATIONS_DIR,
        help="directory of numbered SQL migrations"
        f" (default: {DEFAULT_MIGRATIONS_DIR})",
    )
    serve_parser.set_defaults(handler=_cmd_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    ns = _build_parser().parse_args(argv)
    return ns.handler(ns)


if __name__ == "__main__":
    raise SystemExit(main())
