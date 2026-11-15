"""Work-order checklist service for OpsLedger (T028, M4).

Spec M4/T028 acceptance: an incomplete mandatory item prevents completion
(spec §7.4 ``in_progress -> completed`` precondition; APP08: completion
with an open checklist is rejected with state/history unchanged).

Items are one row each in ``checklist_items`` (migration 0013): label,
mandatory flag, completed_at stamp. Completion of the work order is gated
by :func:`checklist_completion_blocked`, which returns the list of open
mandatory labels; an empty list means completion may proceed. The
transition service (T027) consumes this gate for ``completed``.
"""

from __future__ import annotations

import sqlite3
from uuid import uuid4

from opsledger.core.clock import Clock, format_rfc3339
from opsledger.core.context import require_context, require_owned
from opsledger.core.db import transaction
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError

__all__ = [
    "ITEM_ALREADY_COMPLETED_MESSAGE",
    "add_checklist_item",
    "complete_checklist_item",
    "checklist_completion_blocked",
    "list_checklist_items",
]

ITEM_ALREADY_COMPLETED_MESSAGE = "checklist item already completed"

_SELECT_ITEM_SQL = "SELECT * FROM checklist_items WHERE id = ?"


def add_checklist_item(conn, context, *, work_order_id, label, mandatory, clock):
    """Add one checklist item to a work order (mandatory is a bool)."""
    require_context(context)
    if not isinstance(mandatory, bool):
        raise ValidationError("mandatory must be a boolean")
    cleaned_label = label.strip() if isinstance(label, str) else ""
    if not cleaned_label:
        raise ValidationError("label must be a non-empty string")
    work_order = conn.execute("SELECT * FROM work_orders WHERE id = ?", (work_order_id,)).fetchone()
    require_owned(context, work_order, label="work order")
    item_id = "cli-" + uuid4().hex
    timestamp_text = format_rfc3339(clock.now())
    try:
        with transaction(conn) as tx:
            tx.execute(
                "INSERT INTO checklist_items (id, organization_id, work_order_id, label, mandatory, completed_at, created_at)"
                " VALUES (?, ?, ?, ?, ?, NULL, ?)",
                (item_id, context.organization_id, work_order["id"], cleaned_label, 1 if mandatory else 0, timestamp_text),
            )
    except sqlite3.IntegrityError as exc:
        raise ConflictError("unknown work order for checklist item") from exc
    return conn.execute(_SELECT_ITEM_SQL, (item_id,)).fetchone()


def complete_checklist_item(conn, context, *, item_id, clock):
    """Complete one checklist item (stamps completed_at, keeps history)."""
    require_context(context)
    item = conn.execute(_SELECT_ITEM_SQL, (item_id,)).fetchone()
    require_owned(context, item, label="checklist item")
    if item["completed_at"] is not None:
        raise ConflictError(ITEM_ALREADY_COMPLETED_MESSAGE)
    completed_text = format_rfc3339(clock.now())
    with transaction(conn) as tx:
        tx.execute(
            "UPDATE checklist_items SET completed_at = ? WHERE id = ? AND completed_at IS NULL",
            (completed_text, item["id"]),
        )
    return conn.execute(_SELECT_ITEM_SQL, (item_id,)).fetchone()


def checklist_completion_blocked(conn, context, *, work_order_id):
    """Return the open mandatory labels blocking completion (empty = may proceed)."""
    require_context(context)
    rows = conn.execute(
        "SELECT label FROM checklist_items"
        " WHERE organization_id = ? AND work_order_id = ? AND mandatory = 1 AND completed_at IS NULL",
        (context.organization_id, work_order_id),
    ).fetchall()
    return [row["label"] for row in rows]


def list_checklist_items(conn, context, *, work_order_id):
    """List one work order's checklist items in creation order."""
    require_context(context)
    return conn.execute(
        "SELECT * FROM checklist_items"
        " WHERE organization_id = ? AND work_order_id = ?"
        " ORDER BY created_at, id",
        (context.organization_id, work_order_id),
    ).fetchall()
