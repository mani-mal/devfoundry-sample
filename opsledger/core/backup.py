"""T065 backup/restore core for OpsLedger, built on SQLite's online backup API.

Copies databases with :meth:`sqlite3.Connection.backup`: refusal paths run
before any write, so a refused request never creates or touches a target file.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .db import connect
from .errors import ValidationError

__all__ = [
    "backup_database",
    "restore_database",
    "BACKUP_BUSY_SOURCE_MESSAGE",
    "BACKUP_SOURCE_TYPE_MESSAGE",
    "BACKUP_MISSING_MESSAGE",
]

BACKUP_BUSY_SOURCE_MESSAGE = (
    "source database has an open transaction; commit or roll back before backup"
)
BACKUP_SOURCE_TYPE_MESSAGE = "source must be a sqlite3.Connection"
BACKUP_MISSING_MESSAGE = "backup file does not exist"


def backup_database(source: sqlite3.Connection, target_path: str) -> None:
    """Copy the live ``source`` database into ``target_path``.

    Refusals (non-connection source or an open write transaction) are raised
    before anything is written, so no target file is created on refusal.
    An existing file at ``target_path`` is overwritten by SQLite's backup
    semantics; that is intended.
    """
    if not isinstance(source, sqlite3.Connection):
        raise ValidationError(BACKUP_SOURCE_TYPE_MESSAGE)
    if source.in_transaction:
        raise ValidationError(BACKUP_BUSY_SOURCE_MESSAGE)
    target = sqlite3.connect(target_path)
    try:
        source.backup(target)
    finally:
        target.close()
    return None


def restore_database(backup_path: str, target_path: str) -> sqlite3.Connection:
    """Copy ``backup_path`` into ``target_path`` and open it with the profile.

    Returns :func:`connect`-style connection on ``target_path`` (WAL,
    foreign_keys ON, synchronous NORMAL, Row rows). The caller owns closing
    the returned connection.
    """
    if not Path(backup_path).is_file():
        raise ValidationError(BACKUP_MISSING_MESSAGE)
    source = sqlite3.connect(backup_path)
    target = sqlite3.connect(target_path)
    try:
        source.backup(target)
    finally:
        source.close()
        target.close()
    return connect(target_path)
