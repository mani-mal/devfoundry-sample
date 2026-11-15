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
