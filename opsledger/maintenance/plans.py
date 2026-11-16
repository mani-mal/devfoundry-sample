"""Maintenance plan service for OpsLedger (T049).

Scoping rule: maintenance plans are UTC date-based and bound to one site
and one asset. Every lookup is guarded by
:func:`opsledger.core.context.require_owned`: a missing site/asset/plan
and a cross-organization one surface the same NotFoundError — no
existence leak. Writes happen in one explicit transaction per call.
Days are plain integers (no floats); archived assets cannot accept a
maintenance plan and archived plans cannot be archived again.
"""

from __future__ import annotations

import sqlite3
from uuid import uuid4

from opsledger.core.clock import Clock, format_rfc3339
from opsledger.core.context import require_context, require_owned, scoped_all
from opsledger.core.db import transaction
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError

__all__ = [
    "PLAN_NOT_FOUND_MESSAGE",
    "ARCHIVED_ASSET_MESSAGE",
    "DUPLICATE_PLAN_MESSAGE",
    "PLAN_ARCHIVED_MESSAGE",
    "create_maintenance_plan",
    "get_maintenance_plan",
    "list_maintenance_plans",
    "archive_maintenance_plan",
]

PLAN_NOT_FOUND_MESSAGE = "maintenance plan not found"
ARCHIVED_ASSET_MESSAGE = "archived asset cannot accept a maintenance plan"
DUPLICATE_PLAN_MESSAGE = "duplicate maintenance plan"
PLAN_ARCHIVED_MESSAGE = "maintenance plan is archived"


def _require_positive_int(value, message):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValidationError(message)
    return value


def _require_horizon(value):
    _require_positive_int(value, "horizon_days must be an integer between 1 and 366")
    if value > 366:
        raise ValidationError("horizon_days must be an integer between 1 and 366")
    return value


def create_maintenance_plan(conn, context, *, site_id, asset_id, name, description, interval_days, horizon_days, clock):
    """Create one maintenance plan for an owned site and its asset."""
    require_context(context)
    if not isinstance(name, str) or not name.strip():
        raise ValidationError("name is required")
    if not isinstance(description, str) or not description.strip():
        raise ValidationError("description is required")
    name = name.strip()
    description = description.strip()
    _require_positive_int(interval_days, "interval_days must be a positive integer")
    _require_horizon(horizon_days)
    site = conn.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone()
    require_owned(context, site, label="site")
    if site["archived_at"] is not None:
        raise ValidationError("site is archived")
    asset = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    require_owned(context, asset, label="asset")
    if asset["archived_at"] is not None:
        raise ValidationError(ARCHIVED_ASSET_MESSAGE)
    if asset["site_id"] != site_id:
        raise ValidationError("asset belongs to a different site")
    new_plan_id = "mpl-" + uuid4().hex
    timestamp_text = format_rfc3339(clock.now())
    try:
        with transaction(conn) as tx:
            tx.execute(
                "INSERT INTO maintenance_plans (id, organization_id, site_id, asset_id, name, description, interval_days, horizon_days, active, version, created_at, updated_at, archived_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?, NULL)",
                (new_plan_id, context.organization_id, site_id, asset_id, name, description, interval_days, horizon_days, timestamp_text, timestamp_text),
            )
    except sqlite3.IntegrityError as exc:
        raise ConflictError(DUPLICATE_PLAN_MESSAGE) from exc
    return conn.execute(
        "SELECT * FROM maintenance_plans WHERE id = ?", (new_plan_id,)
    ).fetchone()


def get_maintenance_plan(conn, context, *, plan_id):
    """Return one owned maintenance plan row or raise NotFoundError."""
    row = conn.execute("SELECT * FROM maintenance_plans WHERE id = ?", (plan_id,)).fetchone()
    return require_owned(context, row, label="maintenance plan")


def list_maintenance_plans(conn, context, *, active_only=False):
    """List maintenance plans scoped to the authenticated organization."""
    require_context(context)
    if active_only:
        return scoped_all(
            conn,
            context,
            "SELECT * FROM maintenance_plans WHERE active = 1 AND archived_at IS NULL"
            " ORDER BY created_at, id",
        )
    return scoped_all(
        conn,
        context,
        "SELECT * FROM maintenance_plans ORDER BY created_at, id",
    )


def archive_maintenance_plan(conn, context, *, plan_id, expected_version, clock):
    """Archive one owned maintenance plan (guarded, optimistic version)."""
    row = conn.execute("SELECT * FROM maintenance_plans WHERE id = ?", (plan_id,)).fetchone()
    require_owned(context, row, label="maintenance plan")
    if row["archived_at"] is not None:
        raise ConflictError(PLAN_ARCHIVED_MESSAGE)
    timestamp_text = format_rfc3339(clock.now())
    with transaction(conn) as tx:
        cursor = tx.execute(
            "UPDATE maintenance_plans SET archived_at = ?, active = 0, updated_at = ?, version = version + 1"
            " WHERE id = ? AND organization_id = ? AND version = ? AND archived_at IS NULL",
            (timestamp_text, timestamp_text, plan_id, context.organization_id, expected_version),
        )
        if cursor.rowcount != 1:
            raise ConflictError("maintenance plan version conflict; refresh and retry")
    return conn.execute(
        "SELECT * FROM maintenance_plans WHERE id = ?", (plan_id,)
    ).fetchone()
