"""Work-order labor service for OpsLedger (T029, M4).

Spec M4/T029 acceptance: negative minutes refused; edited totals computed
server-side. Money is integer cents; labor uses minutes. Labor cost is
computed SERVER-SIDE with integer round-half-up:

    cost_cents = (rate_cents_per_hour * minutes + 30) // 60

Locked fixture (doc/): 90 minutes at 8,000 cents/hour = 12,000 cents
exactly; 100 minutes at 8,000 = 13,333 cents (round-half-up of
13,333.33...). The entry stores its rate and computed cost at write time;
later catalog/rate changes never rewrite history (spec §6). Entries are
immutable: no update or delete paths exist.
"""

from __future__ import annotations

import sqlite3
from uuid import uuid4

from opsledger.core.clock import Clock, format_rfc3339
from opsledger.core.context import require_context, require_owned
from opsledger.core.db import transaction
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError

__all__ = [
    "MINUTES_MESSAGE",
    "RATE_MESSAGE",
    "labor_cost_cents",
    "record_labor",
    "labor_total_cents",
    "list_labor_entries",
]

MINUTES_MESSAGE = "minutes must be a positive integer"
RATE_MESSAGE = "rate_cents_per_hour must be a positive integer"

_SELECT_ENTRY_SQL = "SELECT * FROM labor_entries WHERE id = ?"


def labor_cost_cents(minutes, rate_cents_per_hour):
    """Integer round-half-up cost in cents (server-side; no floats)."""
    if not isinstance(minutes, int) or isinstance(minutes, bool) or minutes <= 0:
        raise ValidationError(MINUTES_MESSAGE)
    if not isinstance(rate_cents_per_hour, int) or isinstance(rate_cents_per_hour, bool) or rate_cents_per_hour <= 0:
        raise ValidationError(RATE_MESSAGE)
    return (rate_cents_per_hour * minutes + 30) // 60


def record_labor(conn, context, *, work_order_id, technician_id, minutes, rate_cents_per_hour, clock, note=None):
    """Record one labor entry; the cost is computed server-side and stored."""
    require_context(context)
    cost_cents = labor_cost_cents(minutes, rate_cents_per_hour)
    work_order = conn.execute("SELECT * FROM work_orders WHERE id = ?", (work_order_id,)).fetchone()
    require_owned(context, work_order, label="work order")
    entry_id = "lbr-" + uuid4().hex
    timestamp_text = format_rfc3339(clock.now())
    cleaned_note = note.strip() if isinstance(note, str) and note.strip() else None
    try:
        with transaction(conn) as tx:
            tx.execute(
                "INSERT INTO labor_entries (id, organization_id, work_order_id, technician_id, minutes, rate_cents_per_hour, cost_cents, note, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (entry_id, context.organization_id, work_order["id"], technician_id, minutes, rate_cents_per_hour, cost_cents, cleaned_note, timestamp_text),
            )
    except sqlite3.IntegrityError as exc:
        raise ConflictError("unknown work order for labor entry") from exc
    return conn.execute(_SELECT_ENTRY_SQL, (entry_id,)).fetchone()


def labor_total_cents(conn, context, *, work_order_id):
    """Aggregate the recorded entry costs for one work order (integer cents)."""
    require_context(context)
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_cents), 0) FROM labor_entries"
        " WHERE organization_id = ? AND work_order_id = ?",
        (context.organization_id, work_order_id),
    ).fetchone()
    return row[0]


def list_labor_entries(conn, context, *, work_order_id):
    """List one work order's labor entries in creation order."""
    require_context(context)
    return conn.execute(
        "SELECT * FROM labor_entries"
        " WHERE organization_id = ? AND work_order_id = ?"
        " ORDER BY created_at, id",
        (context.organization_id, work_order_id),
    ).fetchall()
