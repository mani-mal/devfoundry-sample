"""T067 bounded contention core for OpsLedger.

Write transactions with bounded lock retries, mapped to ConflictError on
exhaustion.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from typing import Any

from .errors import ConflictError

DB_LOCKED_CONFLICT_MESSAGE = "database is locked by another writer; retry the operation"


def run_locked(
    conn: sqlite3.Connection,
    fn: Callable[[sqlite3.Connection], Any],
    *,
    max_attempts: int = 3,
    sleeper: Callable[[float], None] = time.sleep,
) -> Any:
    """Run ``fn(conn)`` inside one IMMEDIATE transaction with bounded retries.

    Retries only when the database is locked by another writer; exhaustion
    raises ConflictError (HTTP 409) from the original error.
    """
    attempts = 0
    while True:
        attempts += 1
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower():
                raise
            if attempts >= max_attempts:
                raise ConflictError(DB_LOCKED_CONFLICT_MESSAGE) from exc
            sleeper(0.05 * attempts)
            continue
        break
    try:
        result = fn(conn)
    except BaseException:
        conn.rollback()
        raise
    conn.commit()
    return result


__all__ = ["DB_LOCKED_CONFLICT_MESSAGE", "run_locked"]
