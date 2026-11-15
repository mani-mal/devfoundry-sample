"""Purchase request service for OpsLedger (T041, M6).

Purchase requests are drafts until submitted (a follow-up task
transitions them). Business rules live here in the domain service —
never in HTTP adapters. Every lookup and mutation takes the
authenticated organization context and surfaces one canonical message
for unknown and cross-organization ids: no existence leak.
"""

from __future__ import annotations

from uuid import uuid4

from opsledger.core.clock import format_rfc3339
from opsledger.core.context import require_context, require_owned, scoped_all
from opsledger.core.db import transaction
from opsledger.core.errors import NotFoundError, ValidationError

__all__ = [
    "REQUEST_NOT_FOUND_MESSAGE",
    "create_purchase_request",
    "get_purchase_request",
    "list_purchase_requests",
    "list_request_lines",
    "request_total_cents",
]

REQUEST_NOT_FOUND_MESSAGE = "purchase request not found"

_SELECT_REQUEST_SQL = "SELECT * FROM purchase_requests WHERE id = ?"

_SELECT_VENDOR_SQL = "SELECT * FROM vendors WHERE id = ?"

_SELECT_PART_SQL = "SELECT * FROM parts WHERE id = ?"


def _validate_line(line: object) -> None:
    """Validate one line dict: mapping, required keys, positive integer quantity,
    non-negative integer unit cost (bools and floats refused)."""
    if not isinstance(line, dict):
        raise ValidationError("each line must be a dict")
    for key in ("part_id", "quantity", "unit_cost_cents"):
        if key not in line:
            raise ValidationError("each line requires part_id, quantity, and unit_cost_cents")
    quantity = line["quantity"]
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise ValidationError("line quantity must be a positive integer")
    unit_cost = line["unit_cost_cents"]
    if isinstance(unit_cost, bool) or not isinstance(unit_cost, int) or unit_cost < 0:
        raise ValidationError("line unit_cost_cents must be a non-negative integer")


def _require_vendor_exists(conn: object, context: object, vendor_id: object) -> None:
    """Require the vendor to exist inside the actor's organization."""
    row = conn.execute(_SELECT_VENDOR_SQL, (vendor_id,)).fetchone()
    if row is None or row["organization_id"] != context.organization_id:
        raise NotFoundError(REQUEST_NOT_FOUND_MESSAGE)
    if row["archived_at"] is not None:
        raise ValidationError("archived vendors cannot receive purchase requests")


def _require_part_exists(conn: object, context: object, part_id: object) -> None:
    """Require the part to exist inside the actor's organization."""
    row = conn.execute(_SELECT_PART_SQL, (part_id,)).fetchone()
    if row is None or row["organization_id"] != context.organization_id:
        raise NotFoundError(REQUEST_NOT_FOUND_MESSAGE)
    if row["archived_at"] is not None:
        raise ValidationError("archived parts cannot be added to a purchase request")


def create_purchase_request(conn, context, *, vendor_id, lines, clock):
    """Insert one draft request plus its lines in one explicit transaction."""
    require_context(context)
    if not isinstance(lines, list):
        raise ValidationError("lines must be a list")
    for line in lines:
        _validate_line(line)
    _require_vendor_exists(conn, context, vendor_id)
    for line in lines:
        _require_part_exists(conn, context, line["part_id"])
    total_cents = sum(line["quantity"] * line["unit_cost_cents"] for line in lines)
    request_id = "prq-" + uuid4().hex
    timestamp_text = format_rfc3339(clock.now())
    with transaction(conn) as tx:
        tx.execute(
            "INSERT INTO purchase_requests (id, organization_id, vendor_id, requested_by, status, total_cents, version, created_at, updated_at, archived_at)"
            " VALUES (?, ?, ?, ?, 'draft', ?, 1, ?, ?, NULL)",
            (
                request_id,
                context.organization_id,
                vendor_id,
                context.actor_id,
                total_cents,
                timestamp_text,
                timestamp_text,
            ),
        )
        for line in lines:
            line_id = "prl-" + uuid4().hex
            tx.execute(
                "INSERT INTO purchase_request_lines (id, organization_id, purchase_request_id, part_id, quantity, unit_cost_cents, created_at, updated_at, archived_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    line_id,
                    context.organization_id,
                    request_id,
                    line["part_id"],
                    line["quantity"],
                    line["unit_cost_cents"],
                    timestamp_text,
                    timestamp_text,
                ),
            )
    return conn.execute(_SELECT_REQUEST_SQL, (request_id,)).fetchone()


def get_purchase_request(conn, context, purchase_request_id):
    """Return one request, or NotFoundError for unknown/cross-org ids (no leak)."""
    require_context(context)
    row = conn.execute(_SELECT_REQUEST_SQL, (purchase_request_id,)).fetchone()
    require_owned(context, row, label="purchase request")
    return row


def list_purchase_requests(conn, context):
    """List requests in scope, oldest first, stable (created_at, id)."""
    require_context(context)
    sql = "SELECT * FROM purchase_requests WHERE organization_id = ? ORDER BY created_at, id"
    return scoped_all(conn, context, sql, (context.organization_id,))


def list_request_lines(conn, context, *, purchase_request_id):
    """Return the live lines of one in-scope request, oldest first."""
    require_context(context)
    request_row = conn.execute(_SELECT_REQUEST_SQL, (purchase_request_id,)).fetchone()
    require_owned(context, request_row, label="purchase request")
    sql = (
        "SELECT * FROM purchase_request_lines"
        " WHERE purchase_request_id = ? AND organization_id = ?"
        " ORDER BY created_at, id"
    )
    rows = conn.execute(sql, (request_row["id"], context.organization_id)).fetchall()
    return [row for row in rows if row["archived_at"] is None]


def request_total_cents(conn, context, *, purchase_request_id):
    """Recompute the integer-cent total over the request's live lines."""
    line_rows = list_request_lines(conn, context, purchase_request_id=purchase_request_id)
    return sum(line["quantity"] * line["unit_cost_cents"] for line in line_rows)
