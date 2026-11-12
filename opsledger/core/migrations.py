"""Migration runner for OpsLedger schema changes (T003).

Schema changes are append-only numbered SQL files (``NNN_name.sql``) in one
directory. The runner creates the ``schema_migrations`` history table,
verifies recorded checksums against the current file bytes, and applies each
not-yet-applied migration inside one IMMEDIATE transaction together with its
history row, so schema statements and their history commit or roll back
together.

- ``migration_id`` is the filename without the ``.sql`` suffix.
- ``checksum`` is the sha256 hex digest of the exact file bytes. A second
  run is a no-op while every recorded checksum still matches the current
  bytes.
- Applied migrations are tamper-evident: if any recorded checksum differs
  from the file's current bytes, :class:`ConflictError` is raised naming the
  migration and nothing is applied — pending migrations included.
- Gaps are allowed: ``001`` can be applied while ``002`` is absent from the
  directory; ``002`` applies when it reappears.

``applied_at`` is RFC3339 UTC ending in ``Z`` with second precision,
produced through the injected ``Clock`` (real wall clock by default).
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path

from .clock import Clock, RealClock
from .db import transaction
from .errors import ConflictError, ValidationError

__all__ = ["migrate"]

_MIGRATION_ID_PATTERN = re.compile(r"^(?P<prefix>\d+)")

_CREATE_HISTORY_TABLE_DDL = """CREATE TABLE IF NOT EXISTS schema_migrations (
    id INTEGER PRIMARY KEY,
    migration_id TEXT NOT NULL UNIQUE,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
)"""

_INSERT_HISTORY_SQL = """INSERT INTO schema_migrations (migration_id, checksum, applied_at)
VALUES (?, ?, ?)"""

_LOAD_HISTORY_SQL = """SELECT migration_id, checksum
FROM schema_migrations
ORDER BY migration_id"""


class _Migration:
    """One not-yet-committed migration file: id, checksum, and SQL text."""

    __slots__ = ("numeric_prefix", "migration_id", "checksum", "statement_text")

    def __init__(
        self,
        numeric_prefix: int,
        migration_id: str,
        checksum: str,
        statement_text: str,
    ) -> None:
        self.numeric_prefix = numeric_prefix
        self.migration_id = migration_id
        self.checksum = checksum
        self.statement_text = statement_text


def _has_effective_sql(chunk: str) -> bool:
    index = 0
    length = len(chunk)
    while index < length:
        char = chunk[index]
        if char == "-" and chunk.startswith("--", index):
            end = chunk.find("\n", index)
            if end == -1:
                return False
            index = end + 1
            continue
        if char == "/" and chunk.startswith("/*", index):
            end = chunk.find("*/", index + 2)
            if end == -1:
                return False
            index = end + 2
            continue
        if not char.isspace():
            return True
        index += 1
    return False


def _split_statements(sql_text: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    index = 0
    length = len(sql_text)
    while index < length:
        char = sql_text[index]
        if char == "-" and sql_text.startswith("--", index):
            end = sql_text.find("\n", index)
            end = length if end == -1 else end
            current.append(sql_text[index:end])
            index = end
            continue
        if char == "/" and sql_text.startswith("/*", index):
            end = sql_text.find("*/", index + 2)
            end = length if end == -1 else end + 2
            current.append(sql_text[index:end])
            index = end
            continue
        if char in ("'", '"'):
            start = index
            index += 1
            while index < length:
                if sql_text[index] == char:
                    if sql_text.startswith(char * 2, index):
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            current.append(sql_text[start:index])
            continue
        if char == ";":
            chunk = "".join(current)
            current = []
            if _has_effective_sql(chunk):
                statements.append(chunk.strip())
            index += 1
            continue
        current.append(char)
        index += 1

    tail = "".join(current)
    if _has_effective_sql(tail):
        statements.append(tail.strip())
    return statements


def _load_file_migrations(directory_path: Path) -> list[_Migration]:
    entries: list[tuple[int, str, Path]] = []
    for path in sorted(directory_path.glob("*.sql")):
        if not path.is_file():
            continue
        stem = path.stem
        match = _MIGRATION_ID_PATTERN.match(stem)
        if match is None:
            raise ValidationError(
                "migration filename must start with a numeric prefix"
                " (NNN_name.sql): " + path.name
            )
        entries.append((int(match.group("prefix")), stem, path))

    entries.sort(key=lambda entry: (entry[0], entry[1]))

    migrations: list[_Migration] = []
    for numeric_prefix, migration_id, path in entries:
        file_bytes = path.read_bytes()
        migrations.append(
            _Migration(
                numeric_prefix,
                migration_id,
                hashlib.sha256(file_bytes).hexdigest(),
                file_bytes.decode("utf-8"),
            )
        )
    return migrations


def _verify_checksums(
    file_migrations: list[_Migration],
    history_rows: list[tuple[str, str]],
) -> None:
    mismatches: list[str] = []
    recorded = dict(history_rows)
    for file_migration in file_migrations:
        if file_migration.migration_id in recorded:
            if recorded[file_migration.migration_id] != file_migration.checksum:
                mismatches.append(file_migration.migration_id)
    if mismatches:
        raise ConflictError(
            "applied migration content changed; its recorded checksum"
            " no longer matches: " + ", ".join(mismatches)
        )


def _apply_migration(
    conn: sqlite3.Connection,
    file_migration: _Migration,
    applied_at: str,
) -> None:
    statements = _split_statements(file_migration.statement_text)
    with transaction(conn) as tx:
        for statement in statements:
            tx.execute(statement)
        tx.execute(
            _INSERT_HISTORY_SQL,
            (file_migration.migration_id, file_migration.checksum, applied_at),
        )


def migrate(
    conn: sqlite3.Connection,
    directory: str | Path,
    *,
    clock: Clock | None = None,
) -> list[str]:
    """Apply pending SQL migrations from ``directory`` to ``conn``.

    Behavior:

    - Creates the ``schema_migrations`` history table when absent (columns:
      ``id`` INTEGER PRIMARY KEY, ``migration_id`` TEXT NOT NULL UNIQUE,
      ``checksum`` TEXT NOT NULL, ``applied_at`` TEXT NOT NULL).
    - Lists ``*.sql`` files and sorts them by their numeric prefix
      (``NNN_name.sql``); a file without a numeric prefix raises
      :class:`ValidationError` with the subclass's stable code
      ``"validation_error"``.
    - Loads the recorded history first: if any already-applied migration's
      file content changed, :class:`ConflictError` naming the
      ``migration_id`` is raised before running anything — nothing is
      applied when any checksum mismatch exists.
    - Each not-yet-applied migration runs inside one :func:`transaction`
      block and the ``(migration_id, checksum, applied_at)`` history row is
      recorded in the same transaction. ``migration_id`` is the filename
      without ``.sql``; ``checksum`` is the sha256 hex digest of the exact
      file bytes.
    - Already-applied migrations with matching recorded checksums are
      skipped, so a second run is a no-op. Missing numbers are allowed and
      apply when they reappear.

    Returns the list of ``migration_id`` values applied in this call, in
    application order. Pass ``clock`` to make ``applied_at`` deterministic
    in tests; the real wall clock is used by default.

    Usage::

        migrate(conn, "opsledger/migrations")
    """
    directory_path = Path(directory)
    if not directory_path.is_dir():
        raise ValidationError("migration directory does not exist")

    clock = clock if clock is not None else RealClock()

    conn.execute(_CREATE_HISTORY_TABLE_DDL)
    file_migrations = _load_file_migrations(directory_path)

    history_rows = [
        (row[0], row[1]) for row in conn.execute(_LOAD_HISTORY_SQL).fetchall()
    ]

    _verify_checksums(file_migrations, history_rows)

    applied = {recorded_id for recorded_id, _ in history_rows}
    applied_ids: list[str] = []
    for file_migration in file_migrations:
        if file_migration.migration_id in applied:
            continue
        _apply_migration(conn, file_migration, clock.timestamp())
        applied_ids.append(file_migration.migration_id)
    return applied_ids
