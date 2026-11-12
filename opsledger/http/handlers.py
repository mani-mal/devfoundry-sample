"""Diagnostics HTTP endpoints: bounded health and readiness (T006).

Two endpoints registered by :func:`build_router`:

- ``GET /api/v1/healthz`` — liveness. Always returns
  ``(200, {"status": "ok"})``; the handler never reads the database.
- ``GET /api/v1/readyz`` — readiness. The handler reads the database the
  router server was configured with (``database_path`` on the request view,
  or the module setting through :func:`configure_readyz`): it opens the
  ``schema_migrations`` history table through a short-lived OpsLedger
  connection.

  - history missing or empty -> 503 ``unready`` (the schema has not been
    migrated);
  - recorded history missing a shipped migration (compared against the
    shipped migrations directory listing) -> 503 ``unready`` naming the
    first five missing ids sorted;
  - otherwise ``(200, {"status": "ready", "migrations": N})`` with N the
    recorded history count.

Responses never contain paths, SQL, secrets, or traceback text. Unexpected
errors inside ``readyz`` go through :func:`error_response_for` (500
``internal_error``, constant message, no exception details).
"""

from __future__ import annotations

import threading
from pathlib import Path

from opsledger.http.envelope import build_error_body, error_response_for, new_request_id

__all__ = [
    "build_router",
    "configure_readyz",
    "healthz_handler",
    "readyz_handler",
]

_MAX_MISSING_IDS = 5

_SCHEMA_TABLE_EXISTS_SQL = (
    "SELECT COUNT(*) FROM sqlite_master"
    " WHERE type = 'table' AND name = 'schema_migrations'"
)

_HISTORY_IDS_SQL = "SELECT migration_id FROM schema_migrations ORDER BY migration_id"

_UNREADY_CODE = "unready"
_UNREADY_MESSAGE = "the schema has not been migrated"

_database_path: str | None = None
_state_lock = threading.Lock()


def configure_readyz(database_path: str | None) -> None:
    """Configure (or clear with ``None``) the database file readyz reads."""
    global _database_path
    with _state_lock:
        _database_path = str(database_path) if database_path else None


def _configured_database_path() -> str | None:
    with _state_lock:
        return _database_path


def healthz_handler(_request) -> tuple[int, dict[str, str]]:
    """Return the bounded liveness body (this shape, nothing more)."""
    return 200, {"status": "ok"}


def _migrations_dir_path() -> Path:
    """Return the shipped migrations directory (package-relative)."""
    return Path(__file__).resolve().parents[1] / "migrations"


def _shipped_migration_ids() -> set[str]:
    """Return the ``migration_id`` values shipped in the fixture directory."""
    return {
        path.stem
        for path in sorted(_migrations_dir_path().glob("*.sql"))
        if path.is_file()
    }


def _unready() -> tuple[int, dict[str, object]]:
    return 503, build_error_body(_UNREADY_CODE, _UNREADY_MESSAGE, new_request_id())


def readyz_handler(_request) -> tuple[int, dict[str, object]]:
    """Return the bounded readiness response for the configured database."""
    try:
        database_path = (
            getattr(_request, "database_path", None) or _configured_database_path()
        )
        if not database_path:
            return _unready()

        from opsledger.core.db import connect

        conn = connect(str(database_path))
        try:
            if conn.execute(_SCHEMA_TABLE_EXISTS_SQL).fetchone()[0] == 0:
                return _unready()
            recorded = [row[0] for row in conn.execute(_HISTORY_IDS_SQL).fetchall()]
        finally:
            conn.close()

        if not recorded:
            return _unready()

        missing = sorted(set(_shipped_migration_ids()) - set(recorded))
        if missing:
            named = ", ".join(missing[:_MAX_MISSING_IDS])
            return 503, build_error_body(
                _UNREADY_CODE,
                _UNREADY_MESSAGE + ": missing " + named,
                new_request_id(),
            )

        return 200, {"status": "ready", "migrations": len(recorded)}
    except Exception as exc:
        return error_response_for(exc, new_request_id())


def build_router(*, database_path: str | None = None):
    """Build the diagnostics router with the two health endpoints.

    Passing ``database_path`` also configures the database file the readyz
    handler reads; the plain call leaves the current setting untouched.
    """
    if database_path is not None:
        configure_readyz(database_path)

    from opsledger.http.router import Router

    router = Router()
    router.add("/api/v1/healthz", "GET", healthz_handler)
    router.add("/api/v1/readyz", "GET", readyz_handler)
    return router
