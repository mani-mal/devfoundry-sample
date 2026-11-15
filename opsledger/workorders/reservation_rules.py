"""Reservation-aware work-order transitions for OpsLedger (T038, M5).

Spec §7.4 × §7.5 (the oracle): Cancelling a work order releases its
outstanding reservations ATOMICALLY (one transaction: reservation rows
released, balances reserved decremented with the reserved floor, release
movements appended, cancel event + audit rows). Completing a work order
with an outstanding reservation (status active, remaining_quantity > 0)
is refused with ConflictError and NOTHING changes (spec APP08: state and
history unchanged). Re-runs the M4 transition lifecycle with the now-
active inventory rules: every cancel/completion still validates the
expected aggregate version, appends ONE work_order_events row and ONE
audit_events row in the same transaction, and refuses invalid transitions
exactly as transitions.py does.
"""

from __future__ import annotations

import json
import sqlite3
from uuid import uuid4

from opsledger.core.clock import Clock, format_rfc3339
from opsledger.core.context import require_context, require_owned
from opsledger.core.db import transaction
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError
from opsledger.workorders.transitions import (
    INVALID_TRANSITION_MESSAGE,
    STALE_WORK_ORDER_VERSION_MESSAGE,
    TRANSITION_REASON_REQUIRED_MESSAGE,
    WORK_ORDER_TRANSITIONS,
)
from opsledger.inventory.release_consume import RESERVATION_NOT_ACTIVE_MESSAGE

__all__ = [
    "COMPLETION_OUTSTANDING_RESERVATION_MESSAGE",
    "transition_work_order_with_reservations",
]

COMPLETION_OUTSTANDING_RESERVATION_MESSAGE = (
    "work order has outstanding reservations; release or consume them first"
)

_SELECT_WORK_ORDER_SQL = "SELECT * FROM work_orders WHERE id = ?"

_SELECT_BALANCE_SQL = (
    "SELECT * FROM stock_balances"
    " WHERE organization_id = ? AND part_id = ? AND stock_location_id = ?"
)

_SELECT_OUTSTANDING_SQL = (
    "SELECT * FROM reservations"
    " WHERE organization_id = ? AND work_order_id = ? AND status = 'active'"
    " AND remaining_quantity > 0"
)

_REASONS_REQUIRED = frozenset({"cancelled", "blocked"})


def _require_reason(to_status, reason):
    if to_status in _REASONS_REQUIRED and not (isinstance(reason, str) and reason.strip()):
        raise ValidationError(TRANSITION_REASON_REQUIRED_MESSAGE)
    return reason.strip() if isinstance(reason, str) else None


def _release_reservation_in_tx(tx, context, reservation, timestamp_text):
    """Release one reservation inside the caller's transaction (T038)."""
    quantity = reservation["remaining_quantity"]
    reservation_updated = tx.execute(
        "UPDATE reservations SET status = 'released', remaining_quantity = 0, updated_at = ?"
        " WHERE id = ? AND status = 'active' AND remaining_quantity >= ?",
        (timestamp_text, reservation["id"], quantity),
    ).rowcount
    if reservation_updated != 1:
        raise ConflictError(RESERVATION_NOT_ACTIVE_MESSAGE)
    balance = tx.execute(
        _SELECT_BALANCE_SQL,
        (context.organization_id, reservation["part_id"], reservation["stock_location_id"]),
    ).fetchone()
    require_owned(context, balance, label="stock balance")
    balance_updated = tx.execute(
        "UPDATE stock_balances SET reserved = reserved - ?, version = version + 1, updated_at = ?"
        " WHERE id = ? AND reserved - ? >= 0",
        (quantity, timestamp_text, balance["id"], quantity),
    ).rowcount
    if balance_updated != 1:
        raise ConflictError("reserved quantity below zero; release refused")
    tx.execute(
        "INSERT INTO stock_movements (id, organization_id, part_id, stock_location_id, operation, on_hand_delta, reserved_delta, reason, work_order_id, actor_id, created_at)"
        " VALUES (?, ?, ?, ?, 'release', 0, ?, ?, ?, ?, ?)",
        (
            "stm-" + uuid4().hex,
            context.organization_id,
            reservation["part_id"],
            reservation["stock_location_id"],
            -quantity,
            "work order cancelled",
            reservation["work_order_id"],
            context.actor_id,
            timestamp_text,
        ),
    )
