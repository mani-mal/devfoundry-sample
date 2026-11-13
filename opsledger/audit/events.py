"""Audit events domain module for OpsLedger: generic event writer (T022, M3).

Scoping rule (spec M3/T022, §7.3): ``audit_events`` is immutable business
history. This module is APPEND-ONLY: there is no UPDATE and no DELETE
statement anywhere in it -- audit rows are inserted once and are never
modified or removed, so the history of a business record is immutable.

Write paths (spec §8.2): :func:`record_event` opens one transaction
per insert; :func:`record_event_in_tx` writes the same INSERT on a
connection that already has one transaction open (the caller owns it), so
changes to business records and their audit/outbox records commit
atomically.

Every lookup and join carries the authenticated organization context: the
reader only ever sees events belonging to its own organization -- one
canonical error message, no existence leak (IDs are not authorization).
"""

from __future__ import annotations

import json
import sqlite3
import uuid

from opsledger.core.clock import Clock, format_rfc3339
from opsledger.core.context import (
    OrganizationContext,
    require_context,
    scoped_all,
)
from opsledger.core.db import transaction
from opsledger.core.errors import ValidationError

__all__ = [
    "AUDIT_ENTITY_ASSET",
    "AUDIT_ENTITY_SITE",
    "record_event",
    "record_event_in_tx",
    "events_for_entity",
]

AUDIT_ENTITY_ASSET = "asset"

AUDIT_ENTITY_SITE = "site"

_SELECT_EVENT_BY_ID_SQL = (
    "SELECT id, organization_id, actor_id, entity_type, entity_id,"
    " operation, details, created_at FROM audit_events WHERE id = ?"
)

_INSERT_EVENT_SQL = (
    "INSERT INTO audit_events (id, organization_id, actor_id, entity_type,"
    " entity_id, operation, details, created_at)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)

_LIST_ENTITY_EVENTS_BASE_SQL = (
    "SELECT id, organization_id, actor_id, entity_type, entity_id,"
    " operation, details, created_at FROM audit_events"
    " WHERE organization_id = ? AND entity_type = ? AND entity_id = ?"
)


def _require_operation(operation: object) -> str:
    """Normalize and validate an operation name; return the stripped value."""
    if not isinstance(operation, str) or not operation.strip():
        raise ValidationError("operation must be a non-empty string")
    stripped = operation.strip()
    if not stripped:
        raise ValidationError("operation must be a non-empty string")
    return stripped


def _require_entity_type(entity_type: object) -> str:
    """Normalize and validate an entity_type; return the stripped value."""
    if not isinstance(entity_type, str) or not entity_type.strip():
        raise ValidationError("entity_type must be a non-empty string")
    return entity_type.strip()


def _require_entity_id(entity_id: object) -> str:
    """Normalize and validate an entity id; return the stripped value."""
    if not isinstance(entity_id, str) or not entity_id.strip():
        raise ValidationError("entity_id must be a non-empty string")
    return entity_id.strip()


def _details_text(details: dict | None) -> str:
    """Serialize details canonically: sorted keys, empty object when absent."""
    if details:
        return json.dumps(details, sort_keys=True)
    return "{}"


def _select_event_row_by_id(conn: object, event_id: str) -> object:
    """SELECT the audit row by id and return it, or None when absent."""
    return conn.execute(_SELECT_EVENT_BY_ID_SQL, (event_id,)).fetchone()


def record_event(
    conn: object,
    context: object,
    *,
    entity_type: str,
    entity_id: str,
    operation: str,
    details: dict | None,
    clock: Clock,
) -> object:
    """Insert one audit event for the authenticated organization.

    require_context(context); entity_type and entity_id must be non-empty
    strings; the operation name is normalized by _require_operation. The
    event id is ``"aud-" + uuid.uuid4().hex``. The INSERT carries
    context.organization_id and context.actor_id; details are serialized
    with json.dumps(details, sort_keys=True) when present, "{}" otherwise;
    created_at is serialized canonically via format_rfc3339(clock.now()).
    The row is inserted inside one transaction(conn) and is re-selected by
    id and returned.
    """
    context = require_context(context)
    validated_entity_type = _require_entity_type(entity_type)
    validated_entity_id = _require_entity_id(entity_id)
    validated_operation = _require_operation(operation)
    event_id = "aud-" + uuid.uuid4().hex
    with transaction(conn) as tx:
        tx.execute(
            _INSERT_EVENT_SQL,
            (
                event_id,
                context.organization_id,
                context.actor_id,
                validated_entity_type,
                validated_entity_id,
                validated_operation,
                _details_text(details),
                format_rfc3339(clock.now()),
            ),
        )
    return _select_event_row_by_id(conn, event_id)


def record_event_in_tx(
    tx_conn: object,
    context: object,
    *,
    entity_type: str,
    entity_id: str,
    operation: str,
    details: dict | None,
    clock: Clock,
) -> object:
    """Insert one audit row on a caller-owned open transaction.

    The SAME INSERT as :func:`record_event` executed on ``tx_conn`` WITHOUT
    opening a transaction: the caller already has one open, and this row
    commits together with the caller's business record change (spec §8.2).
    The row is re-selected on ``tx_conn`` and returned.
    """
    context = require_context(context)
    validated_entity_type = _require_entity_type(entity_type)
    validated_entity_id = _require_entity_id(entity_id)
    validated_operation = _require_operation(operation)
    event_id = "aud-" + uuid.uuid4().hex
    tx_conn.execute(
        _INSERT_EVENT_SQL,
        (
            event_id,
            context.organization_id,
            context.actor_id,
            validated_entity_type,
            validated_entity_id,
            validated_operation,
            _details_text(details),
            format_rfc3339(clock.now()),
        ),
    )
    return _select_event_row_by_id(tx_conn, event_id)


def events_for_entity(
    conn: object,
    context: object,
    *,
    entity_type: str,
    entity_id: str,
) -> list:
    """List the immutable history of one entity, oldest first.

    scoped_all over SELECT ... FROM audit_events WHERE organization_id = ?
    AND entity_type = ? AND entity_id = ? ORDER BY created_at, id -- only
    in-scope rows are returned, in order.
    """
    context = require_context(context)
    sql = _LIST_ENTITY_EVENTS_BASE_SQL + " ORDER BY created_at, id"
    return scoped_all(
        conn,
        context,
        sql,
        (context.organization_id, entity_type, entity_id),
    )
