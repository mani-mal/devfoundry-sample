"""Read-only audit queries for OpsLedger (T062).

This module is READ-ONLY: it performs no writes of any kind -- it never
creates, modifies, or removes rows in the append-only ``audit_events``
table. It only READS the immutable history that ``record_event`` /
``record_event_in_tx`` wrote (the mutation surface lives in
``opsledger.audit.events``), so an authorized reader can list and count
events but can never mutate the audit trail through this module.

Every function requires the "audit.read" permission before any query and
is scoped to the authenticated organization: filters are optional,
AND-combined, and parameterized, and the ``organization_id`` condition is
always part of the WHERE clause. Rows of another organization never
appear, and an entity id that only exists in another organization is
indistinguishable from an unknown one (no existence leak).
"""

from __future__ import annotations

import json

from opsledger.core.context import require_context
from opsledger.core.errors import ValidationError
from opsledger.identity.permissions import require_permission

__all__ = ["query_events", "count_events"]

_FILTER_NAMES = ("entity_type", "entity_id", "operation", "actor_id")


def _filters(organization_id: str, **kwargs: object) -> tuple[str, list]:
    """Validate the optional filters and build a parameterized WHERE clause.

    Every filter is optional; provided filters are AND-combined. A filter
    value that is not a non-empty str or None raises ValidationError.
    """
    clauses = ["organization_id = ?"]
    values: list = [organization_id]
    for name in _FILTER_NAMES:
        raw = kwargs.get(name)
        if raw is None:
            continue
        if not isinstance(raw, str) or not raw:
            raise ValidationError("filter values must be non-empty strings or None")
        clauses.append(f"{name} = ?")
        values.append(raw)
    return " AND ".join(clauses), values


_SELECT_AUDIT_EVENTS_SQL = (
    "SELECT id, actor_id, entity_type, entity_id, operation, details,"
    " created_at FROM audit_events WHERE "
)


def _validate_limit(limit: object) -> int:
    """Validate the limit: an int in 1..200; bools refused."""
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValidationError("limit must be an integer between 1 and 200")
    if not 1 <= limit <= 200:
        raise ValidationError("limit must be an integer between 1 and 200")
    return limit


def _row_to_dict(row: object) -> dict:
    """Convert one SELECT row to the public dict, parsing details JSON."""
    result = {
        "id": row["id"],
        "actor_id": row["actor_id"],
        "entity_type": row["entity_type"],
        "entity_id": row["entity_id"],
        "operation": row["operation"],
        "details": row["details"],
        "created_at": row["created_at"],
    }
    try:
        parsed = json.loads(result["details"])
    except (TypeError, ValueError):
        return result
    if isinstance(parsed, dict):
        result["details"] = parsed
    return result


def query_events(
    conn: object,
    context: object,
    *,
    actor: object,
    entity_type: object = None,
    entity_id: object = None,
    operation: object = None,
    actor_id: object = None,
    limit: object = 50,
) -> list[dict]:
    """List the immutable audit history matching the optional filters.

    require_permission(actor, "audit.read") runs before any query; the
    WHERE clause always binds context.organization_id, the provided
    filters are AND-combined, and rows are returned oldest first
    (created_at, id). Each row is a dict whose details value is the
    stored JSON text parsed to a dict when it parses, else the raw
    string.
    """
    require_permission(actor, "audit.read")
    context = require_context(context)
    where, values = _filters(
        context.organization_id,
        entity_type=entity_type,
        entity_id=entity_id,
        operation=operation,
        actor_id=actor_id,
    )
    limit = _validate_limit(limit)
    cursor = conn.execute(
        _SELECT_AUDIT_EVENTS_SQL + where + " ORDER BY created_at, id LIMIT ?",
        (*values, limit),
    )
    return [_row_to_dict(row) for row in cursor.fetchall()]


def count_events(
    conn: object,
    context: object,
    *,
    actor: object,
    entity_type: object = None,
    entity_id: object = None,
    operation: object = None,
    actor_id: object = None,
) -> int:
    """Count the audit rows matching the same filters (no limit).

    require_permission(actor, "audit.read") runs before any query; the
    WHERE clause always binds context.organization_id, so rows of
    another organization never appear and a cross-org entity id returns
    0 without an existence leak.
    """
    require_permission(actor, "audit.read")
    context = require_context(context)
    where, values = _filters(
        context.organization_id,
        entity_type=entity_type,
        entity_id=entity_id,
        operation=operation,
        actor_id=actor_id,
    )
    cursor = conn.execute(
        "SELECT COUNT(*) AS n FROM audit_events WHERE " + where, tuple(values)
    )
    return int(cursor.fetchone()["n"])
