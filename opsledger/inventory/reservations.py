"""Transactional reservation service for OpsLedger (T035, M5).

Spec §7.5 (the oracle): Reserve has on_hand delta 0 and reserved delta
+quantity; the quantity must not exceed available (= on_hand - reserved);
the work order and stock belong to the same authorized site. A refused
reservation changes NOTHING (no movement row, no balance change — the
insufficient-stock refusal is atomic). Every reservation references its
work order; movements are immutable (INSERT-only). Short explicit write
transaction with atomic conditional updates; on contention a bounded
retryable ConflictError (never a traceback).
"""

from __future__ import annotations

import sqlite3
from uuid import uuid4

from opsledger.core.clock import Clock, format_rfc3339
from opsledger.core.context import require_context, require_owned
from opsledger.core.db import transaction
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError

__all__ = [
    "RESERVATION_EXCEEDS_AVAILABLE_MESSAGE",
    "RESERVATION_QUANTITY_MESSAGE",
    "reserve_stock",
]

RESERVATION_EXCEEDS_AVAILABLE_MESSAGE = "reservation exceeds available stock"
RESERVATION_QUANTITY_MESSAGE = "quantity must be a positive integer"


def reserve_stock(conn, context, *, part_id, location_id, work_order_id, quantity, expected_version, actor_id, clock):
    """Reserve stock for one work order; refused when quantity > available."""
    require_context(context)
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
        raise ValidationError(RESERVATION_QUANTITY_MESSAGE)
    work_order = conn.execute("SELECT * FROM work_orders WHERE id = ?", (work_order_id,)).fetchone()
    require_owned(context, work_order, label="work order")
    balance = conn.execute(
        "SELECT * FROM stock_balances WHERE organization_id = ? AND part_id = ? AND stock_location_id = ?",
        (context.organization_id, part_id, location_id),
    ).fetchone()
    require_owned(context, balance, label="stock balance")
    if balance["version"] != expected_version:
        raise ConflictError("stock balance version conflict; retry with the current version")
    available = balance["on_hand"] - balance["reserved"]
    if quantity > available:
        raise ConflictError(RESERVATION_EXCEEDS_AVAILABLE_MESSAGE)
    movement_id = "stm-" + uuid4().hex
    reservation_id = "rsv-" + uuid4().hex
    timestamp_text = format_rfc3339(clock.now())
    with transaction(conn) as tx:
        updated = tx.execute(
            "UPDATE stock_balances SET reserved = reserved + ?, version = version + 1, updated_at = ?"
            " WHERE id = ? AND version = ? AND on_hand - (reserved + ?) >= 0",
            (quantity, timestamp_text, balance["id"], expected_version, quantity),
        ).rowcount
        if updated != 1:
            raise ConflictError(RESERVATION_EXCEEDS_AVAILABLE_MESSAGE)
        tx.execute(
            "INSERT INTO reservations (id, organization_id, part_id, stock_location_id, work_order_id, quantity, remaining_quantity, status, created_at, updated_at, released_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, NULL)",
            (reservation_id, context.organization_id, part_id, location_id, work_order_id, quantity, quantity, timestamp_text, timestamp_text),
        )
        tx.execute(
            "INSERT INTO stock_movements (id, organization_id, part_id, stock_location_id, operation, on_hand_delta, reserved_delta, reason, work_order_id, actor_id, created_at)"
            " VALUES (?, ?, ?, ?, 'reserve', 0, ?, NULL, ?, ?, ?)",
            (movement_id, context.organization_id, part_id, location_id, quantity, work_order_id, actor_id, timestamp_text),
        )
    return conn.execute(
        "SELECT * FROM reservations WHERE id = ?", (reservation_id,)
    ).fetchone()
