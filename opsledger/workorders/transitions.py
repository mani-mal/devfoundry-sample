"""Work-order transition service for OpsLedger (T027, M4).

Spec §7.4 transitions (the oracle):
    open          -> assigned, cancelled
    assigned      -> in_progress, open, cancelled
    in_progress   -> blocked, completed, cancelled
    blocked       -> in_progress, cancelled
    completed     -> closed, in_progress
    closed        -> open
    cancelled     -> (none)

Each transition checks the expected aggregate version (stale -> retryable
ConflictError). Every state change appends ONE work_order_events row and
ONE audit_events row in the SAME transaction (immutable history; the
application never UPDATEs or DELETEs events). Cancel/block/unblock require
a reason; replaying an already-applied transition with the same key and
payload is rejected with a conflict (no duplicate event rows).
"""

from __future__ import annotations

import json
import sqlite3
from uuid import uuid4

from opsledger.core.clock import Clock, format_rfc3339
from opsledger.core.context import require_context, require_owned
from opsledger.core.db import transaction
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError

__all__ = [
    "WORK_ORDER_TRANSITIONS",
    "TRANSITION_REASON_REQUIRED_MESSAGE",
    "INVALID_TRANSITION_MESSAGE",
    "STALE_WORK_ORDER_VERSION_MESSAGE",
    "transition_work_order",
]

WORK_ORDER_TRANSITIONS = {
    "open": ("assigned", "cancelled"),
    "assigned": ("in_progress", "open", "cancelled"),
    "cancelled": (),
    "in_progress": ("blocked", "completed", "cancelled"),
    "blocked": ("in_progress", "cancelled"),
    "completed": ("closed", "in_progress"),
    "closed": ("open",),
}

TRANSITION_REASON_REQUIRED_MESSAGE = "a reason is required for this transition"
CHECKLIST_INCOMPLETE_MESSAGE = "work order has incomplete mandatory checklist items"
INVALID_TRANSITION_MESSAGE = "transition is not allowed from the current state"
STALE_WORK_ORDER_VERSION_MESSAGE = "work order version conflict; refresh and retry"

_SELECT_WORK_ORDER_SQL = "SELECT * FROM work_orders WHERE id = ?"

_REASONS_REQUIRED = frozenset({"cancelled", "blocked"})


def _require_reason(to_status, reason):
    if to_status in _REASONS_REQUIRED and not (isinstance(reason, str) and reason.strip()):
        raise ValidationError(TRANSITION_REASON_REQUIRED_MESSAGE)
    return reason.strip() if isinstance(reason, str) else None


def transition_work_order(conn, context, *, work_order_id, to_status, expected_version, reason, actor_id, clock):
    """Apply one validated transition with its event + audit rows (spec §7.4)."""
    require_context(context)
    if not isinstance(expected_version, int) or isinstance(expected_version, bool) or expected_version <= 0:
        raise ValidationError("expected_version must be a positive integer")
    cleaned_reason = _require_reason(to_status, reason)
    work_order = conn.execute(_SELECT_WORK_ORDER_SQL, (work_order_id,)).fetchone()
    require_owned(context, work_order, label="work order")
    current_status = work_order["status"]
    if to_status not in WORK_ORDER_TRANSITIONS.get(current_status, ()):
        raise ConflictError(INVALID_TRANSITION_MESSAGE)
    work_order_id_val = work_order["id"]
    if to_status == "completed":
        blocked = conn.execute(
            "SELECT label FROM checklist_items"
            " WHERE organization_id = ? AND work_order_id = ? AND mandatory = 1 AND completed_at IS NULL",
            (context.organization_id, work_order_id_val),
        ).fetchall()
        if blocked:
            raise ConflictError(CHECKLIST_INCOMPLETE_MESSAGE)
    timestamp_text = format_rfc3339(clock.now())
    event_id = "woe-" + uuid4().hex
    try:
        with transaction(conn) as tx:
            cursor = tx.execute(
                "UPDATE work_orders SET status = ?, version = version + 1, updated_at = ?"
                " WHERE id = ? AND version = ?",
                (to_status, timestamp_text, work_order_id_val, expected_version),
            )
            if cursor.rowcount == 0:
                raise ConflictError(STALE_WORK_ORDER_VERSION_MESSAGE)
            tx.execute(
                "INSERT INTO work_order_events (id, organization_id, work_order_id, from_status, to_status, reason, actor_id, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (event_id, context.organization_id, work_order_id_val, current_status, to_status, cleaned_reason, actor_id, timestamp_text),
            )
            from opsledger.audit import record_event_in_tx
            record_event_in_tx(
                tx,
                context,
                entity_type="work_order",
                entity_id=work_order_id_val,
                operation="work_order.transition",
                details={"from_status": current_status, "to_status": to_status, "reason": cleaned_reason, "from_version": expected_version, "to_version": expected_version + 1},
                clock=clock,
            )
    except sqlite3.IntegrityError as exc:
        raise ConflictError("duplicate transition event") from exc
    return conn.execute(_SELECT_WORK_ORDER_SQL, (work_order_id_val,)).fetchone()
