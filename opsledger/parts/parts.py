"""Parts and stock-location service for OpsLedger (T033, M5).

Scoping rule (spec M5/T033): part SKUs are scoped per organization via the
``UNIQUE (organization_id, sku)`` constraint, and stock-location codes via
``UNIQUE (organization_id, code)``; a same-org duplicate is refused with
the one canonical message (nothing stored); the same SKU in another
organization is allowed. Every lookup is guarded by
:func:`opsledger.core.context.require_owned`: a missing part/location and a
cross-organization one surface the same NotFoundError — no existence leak.
Both services follow the landed create/list/get pattern (orders.py,
sites.py): thin validation, explicit transaction, re-select and return.
"""

from __future__ import annotations

import sqlite3
from uuid import uuid4

from opsledger.core.clock import Clock, format_rfc3339
from opsledger.core.context import require_context, require_owned, scoped_all
from opsledger.core.db import transaction
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError

__all__ = [
    "DUPLICATE_PART_SKU_MESSAGE",
    "DUPLICATE_STOCK_LOCATION_CODE_MESSAGE",
    "PART_NOT_FOUND_MESSAGE",
    "STOCK_LOCATION_NOT_FOUND_MESSAGE",
    "UNIT_OF_MEASURE",
    "create_part",
    "get_part",
    "list_parts",
    "create_stock_location",
    "get_stock_location",
    "list_stock_locations",
]

UNIT_OF_MEASURE = ("unit", "kg", "liter", "meter")
DUPLICATE_PART_SKU_MESSAGE = "part SKU already exists; use a different SKU"
DUPLICATE_STOCK_LOCATION_CODE_MESSAGE = "stock location code already exists; use a different code"
PART_NOT_FOUND_MESSAGE = "part not found"
STOCK_LOCATION_NOT_FOUND_MESSAGE = "stock location not found"

_SELECT_PART_SQL = "SELECT * FROM parts WHERE id = ?"
_SELECT_STOCK_LOCATION_SQL = "SELECT * FROM stock_locations WHERE id = ?"


def create_part(conn, context, *, sku, name, unit_of_measure, standard_cost_cents, clock):
    """Create one part scoped to the organization; SKU unique per org."""
    require_context(context)
    sku = sku.strip()
    name = name.strip()
    if not sku or not name:
        raise ValidationError("sku and name are required")
    if unit_of_measure not in UNIT_OF_MEASURE:
        raise ValidationError("unit_of_measure must be one of: unit, kg, liter, meter")
    if not isinstance(standard_cost_cents, int) or isinstance(standard_cost_cents, bool) or standard_cost_cents < 0:
        raise ValidationError("standard_cost_cents must be a non-negative integer")
    part_id = "prt-" + uuid4().hex
    timestamp_text = format_rfc3339(clock.now())
    try:
        with transaction(conn) as tx:
            tx.execute(
                "INSERT INTO parts (id, organization_id, sku, name, unit_of_measure, standard_cost_cents, version, created_at, updated_at, archived_at)"
                " VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, NULL)",
                (part_id, context.organization_id, sku, name, unit_of_measure, standard_cost_cents, timestamp_text, timestamp_text),
            )
    except sqlite3.IntegrityError as exc:
        raise ConflictError(DUPLICATE_PART_SKU_MESSAGE) from exc
    return conn.execute(_SELECT_PART_SQL, (part_id,)).fetchone()


def get_part(conn, context, part_id):
    """Return one part, or NotFoundError for unknown/cross-org ids (no leak)."""
    require_context(context)
    row = conn.execute(_SELECT_PART_SQL, (part_id,)).fetchone()
    require_owned(context, row, label="part")
    return row


def list_parts(conn, context):
    """List parts in scope, oldest first, stable (created_at, id)."""
    require_context(context)
    sql = "SELECT * FROM parts WHERE organization_id = ? ORDER BY created_at, id"
    return scoped_all(conn, context, sql, (context.organization_id,))


def create_stock_location(conn, context, *, code, name, clock):
    """Create one stock location scoped to the organization; code unique per org."""
    require_context(context)
    code = code.strip()
    name = name.strip()
    if not code or not name:
        raise ValidationError("code and name are required")
    location_id = "stl-" + uuid4().hex
    timestamp_text = format_rfc3339(clock.now())
    try:
        with transaction(conn) as tx:
            tx.execute(
                "INSERT INTO stock_locations (id, organization_id, code, name, version, created_at, updated_at, archived_at)"
                " VALUES (?, ?, ?, ?, 1, ?, ?, NULL)",
                (location_id, context.organization_id, code, name, timestamp_text, timestamp_text),
            )
    except sqlite3.IntegrityError as exc:
        raise ConflictError(DUPLICATE_STOCK_LOCATION_CODE_MESSAGE) from exc
    return conn.execute(_SELECT_STOCK_LOCATION_SQL, (location_id,)).fetchone()


def get_stock_location(conn, context, location_id):
    """Return one stock location, or NotFoundError for unknown/cross-org ids."""
    require_context(context)
    row = conn.execute(_SELECT_STOCK_LOCATION_SQL, (location_id,)).fetchone()
    require_owned(context, row, label="stock location")
    return row


def list_stock_locations(conn, context):
    """List stock locations in scope, oldest first, stable (created_at, id)."""
    require_context(context)
    sql = "SELECT * FROM stock_locations WHERE organization_id = ? ORDER BY created_at, id"
    return scoped_all(conn, context, sql, (context.organization_id,))
