"""Vendor service for OpsLedger (T041, M6).

Scoping rule (spec M6/T041): a vendor belongs to exactly one organization
and vendor names are unique per organization via the
``UNIQUE (organization_id, name)`` constraint; a same-org duplicate is
refused with the one canonical message (nothing stored); the same name in
another organization is allowed. Every lookup is guarded by
:func:`opsledger.core.context.require_owned`: a missing vendor and a
cross-organization one surface the same NotFoundError — no existence leak.
The service mirrors the landed create/get/list pattern: thin validation,
explicit transaction, re-select and return.
"""

from __future__ import annotations

import sqlite3
from uuid import uuid4

from opsledger.core.clock import format_rfc3339
from opsledger.core.context import require_context, require_owned, scoped_all
from opsledger.core.db import transaction
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError

__all__ = [
    "VENDOR_NOT_FOUND_MESSAGE",
    "DUPLICATE_VENDOR_NAME_MESSAGE",
    "create_vendor",
    "get_vendor",
    "list_vendors",
]

VENDOR_NOT_FOUND_MESSAGE = "vendor not found"
DUPLICATE_VENDOR_NAME_MESSAGE = "vendor name already exists; use a different name"

_SELECT_VENDOR_SQL = "SELECT * FROM vendors WHERE id = ?"


def create_vendor(conn, context, *, name, contact_email, clock):
    """Create one vendor scoped to the organization; name unique per org."""
    require_context(context)
    name = name.strip() if isinstance(name, str) else ""
    if not name:
        raise ValidationError("name is required")
    if contact_email is not None:
        if not isinstance(contact_email, str):
            raise ValidationError("contact_email must be a non-empty string")
        contact_email = contact_email.strip()
        if not contact_email:
            raise ValidationError("contact_email must be a non-empty string")
    vendor_id = "ven-" + uuid4().hex
    timestamp_text = format_rfc3339(clock.now())
    try:
        with transaction(conn) as tx:
            tx.execute(
                "INSERT INTO vendors (id, organization_id, name, contact_email, version, created_at, updated_at, archived_at)"
                " VALUES (?, ?, ?, ?, 1, ?, ?, NULL)",
                (vendor_id, context.organization_id, name, contact_email, timestamp_text, timestamp_text),
            )
    except sqlite3.IntegrityError as exc:
        raise ConflictError(DUPLICATE_VENDOR_NAME_MESSAGE) from exc
    return conn.execute(_SELECT_VENDOR_SQL, (vendor_id,)).fetchone()


def get_vendor(conn, context, vendor_id):
    """Return one vendor, or NotFoundError for unknown/cross-org ids (no leak)."""
    require_context(context)
    row = conn.execute(_SELECT_VENDOR_SQL, (vendor_id,)).fetchone()
    require_owned(context, row, label="vendor")
    return row


def list_vendors(conn, context):
    """List vendors in scope, oldest first, stable (created_at, id)."""
    require_context(context)
    sql = "SELECT * FROM vendors WHERE organization_id = ? ORDER BY created_at, id"
    return scoped_all(conn, context, sql, (context.organization_id,))
