"""Work-order assignment service for OpsLedger (T026, M4).

Spec M4/T026 acceptance: assignment requires an ACTIVE technician in the
same site; cross-site and inactive assignees are denied. One ACTIVE
assignment per work order (the partial unique index from migration 0011);
releasing keeps the history. The work order must be in ``open`` state
(spec §7.4: ``open -> assigned``).
"""

from __future__ import annotations

import sqlite3
from uuid import uuid4

from opsledger.core.clock import Clock, format_rfc3339
from opsledger.core.context import require_context, require_owned
from opsledger.core.db import transaction
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError, PermissionDeniedError

__all__ = [
    "WORK_ORDER_NOT_OPEN_MESSAGE",
    "ASSIGNEE_NOT_ACTIVE_TECHNICIAN_MESSAGE",
    "ACTIVE_ASSIGNMENT_EXISTS_MESSAGE",
    "assign_technician",
    "release_assignment",
]

WORK_ORDER_NOT_OPEN_MESSAGE = "work order is not open"
ASSIGNEE_NOT_ACTIVE_TECHNICIAN_MESSAGE = "assignee must be an active technician with access to the site"
ACTIVE_ASSIGNMENT_EXISTS_MESSAGE = "work order already has an active assignment"

_SELECT_ASSIGNMENT_SQL = "SELECT * FROM assignments WHERE id = ?"


def _technician_active_in_site(conn, organization_id, technician_id, site_id):
    """True only when the technician has an active site membership for the site."""
    row = conn.execute(
        "SELECT 1 FROM site_memberships"
        " WHERE organization_id = ? AND site_id = ? AND user_id = ? AND revoked_at IS NULL",
        (organization_id, site_id, technician_id),
    ).fetchone()
    return row is not None


def assign_technician(conn, context, *, work_order_id, technician_id, assigned_by_id, clock):
    """Assign one active technician to an open work order (spec §7.4)."""
    require_context(context)
    work_order = conn.execute("SELECT * FROM work_orders WHERE id = ?", (work_order_id,)).fetchone()
    require_owned(context, work_order, label="work order")
    if work_order["status"] != "open":
        raise ConflictError(WORK_ORDER_NOT_OPEN_MESSAGE)
    if not _technician_active_in_site(conn, context.organization_id, technician_id, work_order["site_id"]):
        raise PermissionDeniedError(ASSIGNEE_NOT_ACTIVE_TECHNICIAN_MESSAGE)
    work_order_id_val = work_order["id"]
    site_id = work_order["site_id"]
    assignment_id = "asg-" + uuid4().hex
    timestamp_text = format_rfc3339(clock.now())
    try:
        with transaction(conn) as tx:
            tx.execute(
                "INSERT INTO assignments (id, organization_id, work_order_id, site_id, technician_id, assigned_by_id, created_at, released_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                (assignment_id, context.organization_id, work_order_id_val, site_id, technician_id, assigned_by_id, timestamp_text),
            )
            tx.execute(
                "UPDATE work_orders SET status = 'assigned', version = version + 1, updated_at = ? WHERE id = ?",
                (timestamp_text, work_order_id_val),
            )
    except sqlite3.IntegrityError as exc:
        raise ConflictError(ACTIVE_ASSIGNMENT_EXISTS_MESSAGE) from exc
    return conn.execute(_SELECT_ASSIGNMENT_SQL, (assignment_id,)).fetchone()


def release_assignment(conn, context, *, assignment_id, clock):
    """Release one active assignment; keep the history (released_at stamped)."""
    require_context(context)
    assignment = conn.execute("SELECT * FROM assignments WHERE id = ?", (assignment_id,)).fetchone()
    require_owned(context, assignment, label="assignment")
    if assignment["released_at"] is not None:
        raise ConflictError("assignment already released")
    released_text = format_rfc3339(clock.now())
    with transaction(conn) as tx:
        tx.execute(
            "UPDATE assignments SET released_at = ? WHERE id = ?",
            (released_text, assignment_id),
        )
        tx.execute(
            "UPDATE work_orders SET status = 'open', version = version + 1, updated_at = ? WHERE id = ?",
            (released_text, assignment["work_order_id"]),
        )
    return conn.execute(_SELECT_ASSIGNMENT_SQL, (assignment_id,)).fetchone()
