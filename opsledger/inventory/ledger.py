"""Stock balance and movement ledger for OpsLedger (T034, M5).

Spec §7.5 (the oracle): for each part/location, ``available = on_hand -
reserved`` with ``on_hand >= reserved >= 0``; the movement ledger is the
accounting source. The adjust operation is the opening entry: a signed
integer quantity with a REQUIRED reason and supervisor/admin permission
(the permission check lands with the HTTP adapter; the service refuses an
empty reason). A new on-hand cannot fall below reserved (or below zero);
the refused adjustment stores NOTHING (no movement row, no balance
change). Every movement is immutable (INSERT-only, never UPDATEd or
DELETEd); :func:`reconcile_balance` recomputes on-hand/reserved from the
movement sum and reports whether the ledger and the balance agree.
"""

from __future__ import annotations

import sqlite3
from uuid import uuid4

from opsledger.core.clock import Clock, format_rfc3339
from opsledger.core.context import require_context, require_owned, scoped_all
from opsledger.core.db import transaction
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError

__all__ = [
    "REASON_REQUIRED_MESSAGE",
    "INSUFFICIENT_STOCK_MESSAGE",
    "BALANCE_NOT_FOUND_MESSAGE",
    "STOCK_OPERATIONS",
    "adjust_stock",
    "get_balance",
    "get_or_create_balance",
    "list_balances",
    "list_movements",
    "reconcile_balance",
]

REASON_REQUIRED_MESSAGE = "reason is required"
INSUFFICIENT_STOCK_MESSAGE = "insufficient stock; on-hand cannot fall below reserved"
BALANCE_NOT_FOUND_MESSAGE = "stock balance not found"

STOCK_OPERATIONS = ("receive", "reserve", "release", "consume", "adjust")

_SELECT_BALANCE_SQL = "SELECT * FROM stock_balances WHERE id = ?"


def get_or_create_balance(conn, context, *, part_id, location_id, clock):
    """Return the one balance row for (part, location), creating it at zero."""
    require_context(context)
    part = conn.execute("SELECT * FROM parts WHERE id = ?", (part_id,)).fetchone()
    require_owned(context, part, label="part")
    location = conn.execute("SELECT * FROM stock_locations WHERE id = ?", (location_id,)).fetchone()
    require_owned(context, location, label="stock location")
    row = conn.execute(
        "SELECT * FROM stock_balances WHERE organization_id = ? AND part_id = ? AND stock_location_id = ?",
        (context.organization_id, part_id, location_id),
    ).fetchone()
    if row is not None:
        return row
    balance_id = "stb-" + uuid4().hex
    timestamp_text = format_rfc3339(clock.now())
    try:
        with transaction(conn) as tx:
            tx.execute(
                "INSERT INTO stock_balances (id, organization_id, part_id, stock_location_id, on_hand, reserved, version, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, 0, 0, 1, ?, ?)",
                (balance_id, context.organization_id, part_id, location_id, timestamp_text, timestamp_text),
            )
    except sqlite3.IntegrityError as exc:
        raise ConflictError(BALANCE_NOT_FOUND_MESSAGE) from exc
    return conn.execute(_SELECT_BALANCE_SQL, (balance_id,)).fetchone()


def get_balance(conn, context, balance_id):
    """Return one balance row, or NotFoundError for unknown/cross-org ids."""
    require_context(context)
    row = conn.execute(_SELECT_BALANCE_SQL, (balance_id,)).fetchone()
    require_owned(context, row, label="stock balance")
    return row


def list_balances(conn, context):
    """List balances in scope, oldest first, stable (created_at, id)."""
    require_context(context)
    sql = "SELECT * FROM stock_balances WHERE organization_id = ? ORDER BY created_at, id"
    return scoped_all(conn, context, sql, (context.organization_id,))


def list_movements(conn, context, *, part_id, location_id):
    """List the immutable movement ledger for one part/location, oldest first."""
    require_context(context)
    sql = (
        "SELECT * FROM stock_movements WHERE organization_id = ? AND part_id = ?"
        " AND stock_location_id = ? ORDER BY created_at, id"
    )
    return scoped_all(conn, context, sql, (context.organization_id, part_id, location_id))
