"""Corrective actions on incidents for OpsLedger (T054, module).

Corrective actions are the follow-up items raised from one incident;
each carries a required flag, an optional assignee, and a completion
timestamp. Scope rules (spec T054): every lookup is guarded by
:func:`opsledger.core.context.require_owned` so a missing action and an
action owned by another organization surface the same NotFoundError --
no existence leak. Closure rule (spec T054): an incident cannot close
while a required action is open; assignments and completions run as
guarded updates so a concurrent edit surfaces a retryable conflict,
never a traceback or an existence leak.
"""

from __future__ import annotations

from uuid import uuid4

from opsledger.core.clock import format_rfc3339
from opsledger.core.context import require_owned
from opsledger.core.db import transaction
from opsledger.core.errors import ConflictError, ValidationError

__all__ = [
    "ACTION_NOT_FOUND_MESSAGE",
    "ACTION_NOT_OPEN_MESSAGE",
    "ASSIGNEE_NOT_FOUND_MESSAGE",
    "INCIDENT_NOT_OPEN_MESSAGE",
    "OPEN_REQUIRED_ACTION_MESSAGE",
    "add_corrective_action",
    "assign_corrective_action",
    "close_incident",
    "complete_corrective_action",
    "list_corrective_actions",
]

ACTION_NOT_FOUND_MESSAGE = "corrective action not found"
INCIDENT_NOT_OPEN_MESSAGE = "incident is not open"
OPEN_REQUIRED_ACTION_MESSAGE = "incident has open required corrective actions"
ASSIGNEE_NOT_FOUND_MESSAGE = "assignee not found"
ACTION_NOT_OPEN_MESSAGE = "corrective action is not open"

_SELECT_ACTION_SQL = "SELECT * FROM corrective_actions WHERE id = ?"
_SELECT_INCIDENT_SQL = "SELECT * FROM incidents WHERE id = ?"


def _require_name(value, label):
    """Non-blank string check: a non-str (None) raises ValidationError."""
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be a non-blank string")
    trimmed = value.strip()
    if not trimmed:
        raise ValidationError(f"{label} must be a non-blank string")
    return trimmed


def add_corrective_action(conn, context, *, incident_id, title, instructions, required, clock):
    """Add one corrective action to one owned open incident."""
    incident = conn.execute(_SELECT_INCIDENT_SQL, (incident_id,)).fetchone()
    require_owned(context, incident, label="incident")
    if incident["status"] == "closed":
        raise ConflictError(INCIDENT_NOT_OPEN_MESSAGE)
    title_text = _require_name(title, "title")
    instructions_text = _require_name(instructions, "instructions")
    if not isinstance(required, bool):
        raise ValidationError("required must be a boolean")
    action_id = "act-" + uuid4().hex
    timestamp_text = format_rfc3339(clock.now())
    with transaction(conn) as tx:
        tx.execute(
            "INSERT INTO corrective_actions (id, organization_id, incident_id, title, instructions, required, status, assigned_to, due_date, completed_at, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, 'open', NULL, NULL, NULL, ?, ?)",
            (action_id, context.organization_id, incident_id, title_text, instructions_text, 1 if required else 0, timestamp_text, timestamp_text),
        )
    return conn.execute(_SELECT_ACTION_SQL, (action_id,)).fetchone()


def assign_corrective_action(conn, context, *, action_id, assignee_id, clock):
    """Assign one owned open action to a verified assignee."""
    action = conn.execute(_SELECT_ACTION_SQL, (action_id,)).fetchone()
    require_owned(context, action, label="corrective action")
    assignee_text = _require_name(assignee_id, "assignee_id")
    assignee = conn.execute("SELECT 1 FROM users WHERE id = ?", (assignee_text,)).fetchone()
    if assignee is None:
        raise ValidationError(ASSIGNEE_NOT_FOUND_MESSAGE)
    if action["status"] in ("done", "cancelled"):
        raise ConflictError(ACTION_NOT_OPEN_MESSAGE)
    updated_at = format_rfc3339(clock.now())
    with transaction(conn) as tx:
        cursor = tx.execute(
            "UPDATE corrective_actions SET assigned_to = ?, status = 'in_progress', updated_at = ?"
            " WHERE id = ? AND organization_id = ? AND status = 'open'",
            (assignee_text, updated_at, action_id, context.organization_id),
        )
        if cursor.rowcount != 1:
            raise ConflictError("corrective action version conflict; refresh and retry")
    return conn.execute(_SELECT_ACTION_SQL, (action_id,)).fetchone()


def complete_corrective_action(conn, context, *, action_id, clock):
    """Mark one owned open or in-progress action done."""
    action = conn.execute(_SELECT_ACTION_SQL, (action_id,)).fetchone()
    require_owned(context, action, label="corrective action")
    if action["status"] == "done":
        raise ConflictError("corrective action is already done")
    now = format_rfc3339(clock.now())
    with transaction(conn) as tx:
        cursor = tx.execute(
            "UPDATE corrective_actions SET status = 'done', completed_at = ?, updated_at = ?"
            " WHERE id = ? AND organization_id = ? AND status IN ('open', 'in_progress')",
            (now, now, action_id, context.organization_id),
        )
        if cursor.rowcount != 1:
            raise ConflictError("corrective action version conflict; refresh and retry")
    return conn.execute(_SELECT_ACTION_SQL, (action_id,)).fetchone()


def close_incident(conn, context, *, incident_id, expected_version, clock):
    """Close one owned open incident when no required action is open."""
    incident = conn.execute(_SELECT_INCIDENT_SQL, (incident_id,)).fetchone()
    require_owned(context, incident, label="incident")
    if incident["status"] == "closed":
        raise ConflictError(INCIDENT_NOT_OPEN_MESSAGE)
    open_required = conn.execute(
        "SELECT COUNT(*) FROM corrective_actions WHERE incident_id = ? AND required = 1"
        " AND status NOT IN ('done', 'cancelled')",
        (incident_id,),
    ).fetchone()[0]
    if open_required > 0:
        raise ConflictError(OPEN_REQUIRED_ACTION_MESSAGE)
    closed_at = format_rfc3339(clock.now())
    with transaction(conn) as tx:
        cursor = tx.execute(
            "UPDATE incidents SET status = 'closed', closed_at = ?, updated_at = ?, version = version + 1"
            " WHERE id = ? AND organization_id = ? AND version = ? AND status != 'closed'",
            (closed_at, closed_at, incident_id, context.organization_id, expected_version),
        )
        if cursor.rowcount != 1:
            raise ConflictError("incident version conflict; refresh and retry")
    return conn.execute(_SELECT_INCIDENT_SQL, (incident_id,)).fetchone()


def list_corrective_actions(conn, context, *, incident_id):
    """Return the corrective actions for one owned incident, in order."""
    incident = conn.execute(_SELECT_INCIDENT_SQL, (incident_id,)).fetchone()
    require_owned(context, incident, label="incident")
    return list(
        conn.execute(
            "SELECT * FROM corrective_actions WHERE organization_id = ? AND incident_id = ?"
            " ORDER BY created_at, id",
            (context.organization_id, incident_id),
        ).fetchall()
    )
