"""T071 upgrade fixture and restore diagnostics core: builds prior-milestone
databases (migrations applied only through a milestone boundary) and reports
post-upgrade/restore diagnostics.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from .db import connect
from .errors import ValidationError
from .migrations import migrate

__all__ = [
    "MILESTONE_BOUNDARIES",
    "build_prior_database",
    "upgrade_database",
    "restore_diagnostics",
]

MILESTONE_BOUNDARIES: dict[str, str] = {
    "m5": "0017_stock_ledger",
    "m6": "0019_idempotency",
    "m7": "0022_maintenance",
}

_SHIPPED_MIGRATIONS_DIRECTORY = Path(__file__).resolve().parents[1] / "migrations"

_BOUNDARY_PREFIX_PATTERN = re.compile(r"^\d+")

_BOUNDARY_MESSAGE = "boundary must be a numbered migration id like 0017_stock_ledger"

_CONNECTION_MESSAGE = "diagnostics require a sqlite3.Connection"


def _boundary_prefix(boundary: str) -> int:
    """Return the numeric prefix of a numbered migration id boundary.

    The id is a filename stem like ``0017_stock_ledger``; a value without a
    leading digit run is rejected with :class:`ValidationError`.
    """
    match = _BOUNDARY_PREFIX_PATTERN.match(boundary)
    if match is None:
        raise ValidationError(_BOUNDARY_MESSAGE)
    return int(match.group(0))


def build_prior_database(
    target_path: str,
    *,
    boundary: str = "0017_stock_ledger",
    clock: Any | None = None,
) -> sqlite3.Connection:
    """Build a database with migrations applied only through ``boundary``.

    Only shipped migration files whose numeric prefix is at or below the
    boundary's prefix are copied into a scratch directory and applied, so the
    result is exactly a database as a prior milestone would have left it.
    Returns the open connection; the caller owns closing it.
    """
    if not isinstance(target_path, str) or not target_path:
        raise ValidationError("target_path must be a non-empty string")

    cap = _boundary_prefix(boundary)

    scratch = Path(tempfile.mkdtemp(prefix="upgrade-fixture-"))
    conn: sqlite3.Connection | None = None
    try:
        for path in sorted(_SHIPPED_MIGRATIONS_DIRECTORY.glob("*.sql")):
            match = _BOUNDARY_PREFIX_PATTERN.match(path.stem)
            if match is not None and int(match.group(0)) <= cap:
                shutil.copy2(path, scratch / path.name)
        conn = connect(target_path)
        migrate(conn, scratch, clock=clock)
        return conn
    except BaseException:
        if conn is not None:
            conn.close()
        raise
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def upgrade_database(
    conn: sqlite3.Connection,
    *,
    directory: str | Path = "opsledger/migrations",
    clock: Any | None = None,
) -> list[str]:
    """Upgrade an existing database with all pending shipped migrations.

    Returns the list of migration ids applied by this call, in application
    order; a second call is a no-op.
    """
    if not isinstance(conn, sqlite3.Connection):
        raise ValidationError("target must be a sqlite3.Connection")
    return migrate(conn, directory, clock=clock)


def restore_diagnostics(conn: sqlite3.Connection) -> dict[str, Any]:
    """Report post-upgrade/restore diagnostics for ``conn``.

    Collects integrity, foreign key, migration history, and per-table row
    counts; all values reflect a healthy database when ``integrity`` is
    ``"ok"`` and there are no foreign key violations.
    """
    if not isinstance(conn, sqlite3.Connection):
        raise ValidationError(_CONNECTION_MESSAGE)

    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    foreign_key_violations = len(
        conn.execute("PRAGMA foreign_key_check").fetchall()
    )
    applied_migration_count = conn.execute(
        "SELECT COUNT(*) FROM schema_migrations"
    ).fetchone()[0]

    table_names = sorted(
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master"
            " WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    )
    counts = {
        name: conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        for name in table_names
    }

    return {
        "integrity": integrity,
        "foreign_key_violations": foreign_key_violations,
        "applied_migration_count": applied_migration_count,
        "counts": counts,
    }
