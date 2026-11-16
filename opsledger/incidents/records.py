"""Incident records and linked work orders for OpsLedger (T053, module).

Incidents are follow-up records raised after an event at one site. Scope
rules (spec T053): every lookup is guarded by
:func:`opsledger.core.context.require_owned` so a missing incident and an
incident owned by another organization surface the same NotFoundError --
no existence leak. Incident and linked work orders must share both the
organization and the site; the join here only selects rows, and text is
stored verbatim as plain text (rendering it safely is a UI-layer rule,
enforced by tests there).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from uuid import uuid4

from opsledger.core.clock import format_rfc3339
from opsledger.core.context import require_context, require_owned
from opsledger.core.db import transaction
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError

__all__ = [
    "DUPLICATE_LINK_MESSAGE",
    "INCIDENT_CLOSED_MESSAGE",
    "INCIDENT_NOT_FOUND_MESSAGE",
    "LINKED_NOT_FOUND_MESSAGE",
    "SITE_MISMATCH_MESSAGE",
    "create_incident",
    "get_incident",
    "list_incidents",
    "link_work_order",
    "list_linked_work_orders",
]

INCIDENT_NOT_FOUND_MESSAGE = "incident not found"
DUPLICATE_LINK_MESSAGE = "work order already linked to the incident"
LINKED_NOT_FOUND_MESSAGE = "linked work order not found"
SITE_MISMATCH_MESSAGE = "work order belongs to a different site"
INCIDENT_CLOSED_MESSAGE = "incident is closed"

_SEVERITIES = ("low", "medium", "high", "critical")

_SELECT_INCIDENT_SQL = "SELECT * FROM incidents WHERE id = ?"
_SELECT_LINK_SQL = "SELECT * FROM incident_work_orders WHERE id = ?"


def _require_name(value, label):
    """Non-blank string check: a non-str (None) raises ValidationError."""
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be a non-blank string")
    trimmed = value.strip()
    if not trimmed:
        raise ValidationError(f"{label} must be a non-blank string")
    return trimmed


def create_incident(conn, context, *, site_id, asset_id, reported_by, title, description, severity, occurred_at, clock):
    """Create one incident row owned by the authenticated organization."""
    require_context(context)
    reported_by_text = _require_name(reported_by, "reported_by")
    title_text = _require_name(title, "title")
    description_text = _require_name(description, "description")
    if len(title_text) > 200:
        raise ValidationError("title must be at most 200 characters")
    if severity not in _SEVERITIES:
        raise ValidationError("severity must be one of: low, medium, high, critical")
    if occurred_at is not None:
        if not isinstance(occurred_at, str) or not occurred_at.endswith("Z"):
            raise ValidationError("occurred_at must be an RFC3339 Z timestamp")
        try:
            datetime.strptime(occurred_at[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError as exc:
            raise ValidationError("occurred_at must be an RFC3339 Z timestamp") from exc
    site = conn.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone()
    require_owned(context, site, label="site")
    if site["archived_at"] is not None:
        raise ValidationError("site is archived")
    if asset_id is not None:
        asset = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
        require_owned(context, asset, label="asset")
        if asset["archived_at"] is not None:
            raise ValidationError("archived asset cannot be linked to an incident")
        if asset["site_id"] != site_id:
            raise ValidationError("asset belongs to a different site")
    incident_id = "inc-" + uuid4().hex
    timestamp_text = format_rfc3339(clock.now())
    with transaction(conn) as tx:
        tx.execute(
            "INSERT INTO incidents (id, organization_id, site_id, asset_id, reported_by, title, description, severity, status, occurred_at, closed_at, version, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 1, ?, ?)",
            (incident_id, context.organization_id, site_id, asset_id, reported_by_text, title_text, description_text, severity, "open", occurred_at, timestamp_text, timestamp_text),
        )
    return conn.execute(_SELECT_INCIDENT_SQL, (incident_id,)).fetchone()


def get_incident(conn, context, *, incident_id):
    """Return one incident row, or the canonical no-leak NotFoundError."""
    incident = conn.execute(_SELECT_INCIDENT_SQL, (incident_id,)).fetchone()
    return require_owned(context, incident, label="incident")


def list_incidents(conn, context, *, status=None):
    """List incident rows scoped to the authenticated organization."""
    if status is None:
        rows = conn.execute(
            "SELECT * FROM incidents WHERE organization_id = ? ORDER BY created_at, id",
            (context.organization_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM incidents WHERE organization_id = ? AND status = ? ORDER BY created_at, id",
            (context.organization_id, status),
        ).fetchall()
    return list(rows)


def link_work_order(conn, context, *, incident_id, work_order_id, clock):
    """Link one owned work order to one owned open incident."""
    incident = conn.execute(_SELECT_INCIDENT_SQL, (incident_id,)).fetchone()
    require_owned(context, incident, label="incident")
    if incident["status"] == "closed":
        raise ConflictError(INCIDENT_CLOSED_MESSAGE)
    work_order = conn.execute("SELECT * FROM work_orders WHERE id = ?", (work_order_id,)).fetchone()
    require_owned(context, work_order, label="work order")
    if incident["site_id"] != work_order["site_id"]:
        raise ValidationError(SITE_MISMATCH_MESSAGE)
    link_id = "iln-" + uuid4().hex
    try:
        with transaction(conn) as tx:
            tx.execute(
                "INSERT INTO incident_work_orders (id, organization_id, incident_id, work_order_id, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (link_id, context.organization_id, incident_id, work_order_id, format_rfc3339(clock.now())),
            )
    except sqlite3.IntegrityError as exc:
        raise ConflictError(DUPLICATE_LINK_MESSAGE) from exc
    return conn.execute(_SELECT_LINK_SQL, (link_id,)).fetchone()


def list_linked_work_orders(conn, context, *, incident_id):
    """Return the work-order rows linked to one owned incident, in order."""
    incident = conn.execute(_SELECT_INCIDENT_SQL, (incident_id,)).fetchone()
    require_owned(context, incident, label="incident")
    return [
        row
        for row in conn.execute(
            "SELECT wo.* FROM incident_work_orders AS iln"
            " JOIN work_orders AS wo ON wo.id = iln.work_order_id"
            " WHERE iln.organization_id = ? AND iln.incident_id = ?"
            " ORDER BY iln.created_at",
            (context.organization_id, incident_id),
        ).fetchall()
    ]
