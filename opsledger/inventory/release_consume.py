"""Reservation release and consumption for OpsLedger (T036, M5).

Spec §7.5 (the oracle): Release has reserved delta -quantity and must
reference an ACTIVE reservation with sufficient remaining quantity;
Consume has on_hand delta -quantity and reserved delta -quantity and
cannot exceed the remaining reserved quantity. Quantities cannot be
reused: a released or consumed reservation cannot be released or
consumed again (its remaining_quantity and status guard every write).
Every operation writes the reservation UPDATE, the balance UPDATE
(atomic conditional), and the stock_movements INSERT in ONE short
transaction; a refused operation changes NOTHING. Movements stay
immutable (INSERT-only); on contention a retryable ConflictError.
"""

from __future__ import annotations

import sqlite3
from uuid import uuid4

from opsledger.core.clock import Clock, format_rfc3339
from opsledger.core.context import require_context, require_owned
from opsledger.core.db import transaction
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError

__all__ = [
    "RESERVATION_NOT_ACTIVE_MESSAGE",
    "RELEASE_EXCEEDS_REMAINING_MESSAGE",
    "CONSUME_EXCEEDS_REMAINING_MESSAGE",
    "release_reservation",
    "consume_reservation",
]

RESERVATION_NOT_ACTIVE_MESSAGE = "reservation is not active"
RELEASE_EXCEEDS_REMAINING_MESSAGE = "release exceeds remaining reservation quantity"
CONSUME_EXCEEDS_REMAINING_MESSAGE = "consumption exceeds remaining reservation quantity"

_SELECT_RESERVATION_SQL = "SELECT * FROM reservations WHERE id = ?"


def _get_active_reservation(conn, context, reservation_id):
    """Return the reservation row, requiring it to be active and in scope."""
    require_context(context)
    row = conn.execute(_SELECT_RESERVATION_SQL, (reservation_id,)).fetchone()
    require_owned(context, row, label="reservation")
    if row["status"] != "active":
        raise ConflictError(RESERVATION_NOT_ACTIVE_MESSAGE)
    return row


def release_reservation(conn, context, *, reservation_id, quantity, expected_version, actor_id, clock):
    """Release part of one active reservation; reserved delta -quantity."""
    reservation = _get_active_reservation(conn, context, reservation_id)
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
        raise ValidationError("quantity must be a positive integer")
    if quantity > reservation["remaining_quantity"]:
        raise ConflictError(RELEASE_EXCEEDS_REMAINING_MESSAGE)
    balance = conn.execute(
        "SELECT * FROM stock_balances WHERE organization_id = ? AND part_id = ? AND stock_location_id = ?",
        (context.organization_id, reservation["part_id"], reservation["stock_location_id"]),
    ).fetchone()
    require_owned(context, balance, label="stock balance")
    if balance["version"] != expected_version:
        raise ConflictError("stock balance version conflict; retry with the current version")
    new_remaining = reservation["remaining_quantity"] - quantity
    movement_id = "stm-" + uuid4().hex
    timestamp_text = format_rfc3339(clock.now())
    fully_released = new_remaining == 0
    with transaction(conn) as tx:
        reservation_updated = tx.execute(
            "UPDATE reservations SET remaining_quantity = ?, status = ?, updated_at = ?"
            " WHERE id = ? AND status = 'active' AND remaining_quantity >= ?",
            (new_remaining, "released" if fully_released else "active", timestamp_text, reservation["id"], quantity),
        ).rowcount
        if reservation_updated != 1:
            raise ConflictError(RESERVATION_NOT_ACTIVE_MESSAGE)
        balance_updated = tx.execute(
            "UPDATE stock_balances SET reserved = reserved - ?, version = version + 1, updated_at = ?"
            " WHERE id = ? AND version = ? AND reserved - ? >= 0",
            (quantity, timestamp_text, balance["id"], expected_version, quantity),
        ).rowcount
        if balance_updated != 1:
            raise ConflictError("stock balance version conflict; retry with the current version")
        tx.execute(
            "INSERT INTO stock_movements (id, organization_id, part_id, stock_location_id, operation, on_hand_delta, reserved_delta, reason, work_order_id, actor_id, created_at)"
            " VALUES (?, ?, ?, ?, 'release', 0, ?, NULL, ?, ?, ?)",
            (movement_id, context.organization_id, reservation["part_id"], reservation["stock_location_id"], -quantity, reservation["work_order_id"], actor_id, timestamp_text),
        )
    return conn.execute(_SELECT_RESERVATION_SQL, (reservation["id"],)).fetchone()


def consume_reservation(conn, context, *, reservation_id, quantity, expected_version, actor_id, clock):
    """Consume part of one active reservation; on-hand and reserved both drop."""
    reservation = _get_active_reservation(conn, context, reservation_id)
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
        raise ValidationError("quantity must be a positive integer")
    if quantity > reservation["remaining_quantity"]:
        raise ConflictError(CONSUME_EXCEEDS_REMAINING_MESSAGE)
    balance = conn.execute(
        "SELECT * FROM stock_balances WHERE organization_id = ? AND part_id = ? AND stock_location_id = ?",
        (context.organization_id, reservation["part_id"], reservation["stock_location_id"]),
    ).fetchone()
    require_owned(context, balance, label="stock balance")
    if balance["version"] != expected_version:
        raise ConflictError("stock balance version conflict; retry with the current version")
    new_remaining = reservation["remaining_quantity"] - quantity
    movement_id = "stm-" + uuid4().hex
    timestamp_text = format_rfc3339(clock.now())
    fully_consumed = new_remaining == 0
    with transaction(conn) as tx:
        reservation_updated = tx.execute(
            "UPDATE reservations SET remaining_quantity = ?, status = ?, updated_at = ?"
            " WHERE id = ? AND status = 'active' AND remaining_quantity >= ?",
            (new_remaining, "consumed" if fully_consumed else "active", timestamp_text, reservation["id"], quantity),
        ).rowcount
        if reservation_updated != 1:
            raise ConflictError(RESERVATION_NOT_ACTIVE_MESSAGE)
        balance_updated = tx.execute(
            "UPDATE stock_balances SET on_hand = on_hand - ?, reserved = reserved - ?, version = version + 1, updated_at = ?"
            " WHERE id = ? AND version = ? AND on_hand - ? >= 0 AND reserved - ? >= 0",
            (quantity, quantity, timestamp_text, balance["id"], expected_version, quantity, quantity),
        ).rowcount
        if balance_updated != 1:
            raise ConflictError("stock balance version conflict; retry with the current version")
        tx.execute(
            "INSERT INTO stock_movements (id, organization_id, part_id, stock_location_id, operation, on_hand_delta, reserved_delta, reason, work_order_id, actor_id, created_at)"
            " VALUES (?, ?, ?, ?, 'consume', ?, ?, NULL, ?, ?, ?)",
            (movement_id, context.organization_id, reservation["part_id"], reservation["stock_location_id"], -quantity, -quantity, reservation["work_order_id"], actor_id, timestamp_text),
        )
    return conn.execute(_SELECT_RESERVATION_SQL, (reservation["id"],)).fetchone()
