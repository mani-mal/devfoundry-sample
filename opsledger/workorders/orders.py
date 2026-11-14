"""Work-order create service for OpsLedger (T025, M4).

Scoping rule (spec M4/T025): work order numbers are scoped per
organization via the ``UNIQUE (organization_id, number)`` constraint, so
the same number in another organization is allowed and a same-org
duplicate is refused with the one canonical message
:data:`DUPLICATE_WORK_ORDER_NUMBER_MESSAGE` (nothing stored). Every
lookup is guarded by :func:`opsledger.core.context.require_owned`: a
missing site/asset and a cross-organization site/asset surface the same
NotFoundError — no existence leak. The composite foreign keys from
migration 0010 make a cross-organization site/asset reference impossible
to store; the service also refuses a site/asset mismatch in the same
organization.
"""

from __future__ import annotations

import sqlite3
from uuid import uuid4

from opsledger.core.clock import Clock, format_rfc3339
from opsledger.core.context import require_context, require_owned
from opsledger.core.db import transaction
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError

__all__ = [
    "DUPLICATE_WORK_ORDER_NUMBER_MESSAGE",
    "WORK_ORDER_PRIORITIES",
    "WORK_ORDER_STATUSES",
    "create_work_order",
]

WORK_ORDER_PRIORITIES = ("low", "medium", "high")
WORK_ORDER_STATUSES = ("open", "assigned", "in_progress", "blocked", "completed", "closed", "cancelled")
DUPLICATE_WORK_ORDER_NUMBER_MESSAGE = "work order number already exists; use a different number"

_SELECT_WORK_ORDER_SQL = "SELECT * FROM work_orders WHERE id = ?"


def create_work_order(conn, context, *, site_id, asset_id, number, title, description, priority, requester_id, clock):
    """Create one work order scoped to an owned site and its asset."""
    require_context(context)
    number = number.strip()
    title = title.strip()
    if not number or not title:
        raise ValidationError("number and title are required")
    if priority not in WORK_ORDER_PRIORITIES:
        raise ValidationError("priority must be one of: low, medium, high")
    site = conn.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone()
    require_owned(context, site, label="site")
    if site["archived_at"] is not None:
        raise ValidationError("site is archived")
    asset = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    require_owned(context, asset, label="asset")
    if asset["archived_at"] is not None:
        raise ValidationError("asset is archived")
    if asset["site_id"] != site_id:
        raise ValidationError("asset belongs to a different site")
    work_order_id = "wor-" + uuid4().hex
    timestamp_text = format_rfc3339(clock.now())
    try:
        with transaction(conn) as tx:
            tx.execute(
                "INSERT INTO work_orders (id, organization_id, site_id, asset_id, number, title, description, priority, status, requester_id, version, created_at, updated_at, archived_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (work_order_id, context.organization_id, site_id, asset_id, number, title, description, priority, "open", requester_id, 1, timestamp_text, timestamp_text),
            )
    except sqlite3.IntegrityError as exc:
        raise ConflictError(DUPLICATE_WORK_ORDER_NUMBER_MESSAGE) from exc
    return conn.execute(_SELECT_WORK_ORDER_SQL, (work_order_id,)).fetchone()
