"""Line-edit service for OpsLedger purchase requests (T043, M6).

Adds and edits single lines on draft/submitted purchase requests.
Business rules live here in the domain service — never in HTTP
adapters. Editing a submitted request invalidates approval: every
live approvals row gets invalidated_at stamped (an UPDATE, never a
delete) and the request reverts to draft with the recomputed
integer-cent total, so resubmission is required. Editing an approved
request is refused with the canonical message (cancel and re-create
it). Unknown and cross-organization ids surface one canonical
message: no existence leak.
"""

from __future__ import annotations

from uuid import uuid4

from opsledger.audit import record_event_in_tx
from opsledger.core.clock import Clock, format_rfc3339
from opsledger.core.context import require_context
from opsledger.core.db import transaction
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError
from opsledger.purchasing.requests import request_total_cents

__all__ = [
    "APPROVED_REQUEST_EDIT_MESSAGE",
    "LINE_NOT_FOUND_MESSAGE",
    "add_request_line",
    "update_request_line",
]

APPROVED_REQUEST_EDIT_MESSAGE = (
    "approved purchase request cannot be edited; cancel and re-create it"
)

LINE_NOT_FOUND_MESSAGE = "purchase request line not found"

_SELECT_REQUEST_SQL = "SELECT * FROM purchase_requests WHERE id = ?"

_SELECT_PART_SQL = "SELECT * FROM parts WHERE id = ?"

_SELECT_LINE_SQL = (
    "SELECT * FROM purchase_request_lines"
    " WHERE id = ? AND organization_id = ? AND archived_at IS NULL"
)

_EDITABLE_STATUSES = ("draft", "submitted")

_VERSION_CONFLICT_MESSAGE = "purchase request version conflict; refresh and retry"


def _validate_quantity(quantity: object) -> None:
    """Require a positive integer quantity; bools and floats are refused."""
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise ValidationError("line quantity must be a positive integer")


def _validate_unit_cost(unit_cost_cents: object) -> None:
    """Require a non-negative integer unit cost; bools and floats are refused."""
    if isinstance(unit_cost_cents, bool) or not isinstance(unit_cost_cents, int) or unit_cost_cents < 0:
        raise ValidationError("line unit_cost_cents must be a non-negative integer")


def _editable_request(request_row: object) -> None:
    """Canonical no-leak guard: the edit is accepted only from an editable
    status; any other status raises ConflictError carrying
    APPROVED_REQUEST_EDIT_MESSAGE (the documented contract: cancel and
    re-create it)."""
    if request_row is None:
        raise NotFoundError("purchase request not found")
    if request_row["status"] not in _EDITABLE_STATUSES:
        raise ConflictError(APPROVED_REQUEST_EDIT_MESSAGE)


def _apply_edit(
    tx: object,
    context: object,
    *,
    purchase_request_id: str,
    line_id: str,
    operation: str,
    from_status: str,
    total_cents: int,
    expected_version: int,
    timestamp_text: str,
    clock: Clock,
) -> None:
    """Apply the guarded optimistic-concurrency request UPDATE, the approval
    invalidation for a previously submitted request, and the audit record on
    the open transaction."""
    cursor = tx.execute(
        "UPDATE purchase_requests SET status = CASE WHEN status = 'submitted'"
        " THEN 'draft' ELSE status END, total_cents = ?, version = version + 1,"
        " updated_at = ? WHERE id = ? AND version = ?",
        (total_cents, timestamp_text, purchase_request_id, expected_version),
    )
    if cursor.rowcount != 1:
        raise ConflictError(_VERSION_CONFLICT_MESSAGE)
    if from_status == "submitted":
        tx.execute(
            "UPDATE approvals SET invalidated_at = ?, updated_at = ?"
            " WHERE purchase_request_id = ? AND organization_id = ?"
            " AND invalidated_at IS NULL",
            (timestamp_text, timestamp_text, purchase_request_id, context.organization_id),
        )
    record_event_in_tx(
        tx,
        context,
        entity_type="purchase_request",
        entity_id=purchase_request_id,
        operation=operation,
        details={
            "line_id": line_id,
            "from_status": from_status,
            "from_version": expected_version,
            "to_version": expected_version + 1,
            "total_cents": total_cents,
        },
        clock=clock,
    )


def add_request_line(conn, context, *, purchase_request_id, part_id, quantity, unit_cost_cents, expected_version, clock):
    """Add one line to a draft/submitted request; return the request row."""
    require_context(context)
    _validate_quantity(quantity)
    _validate_unit_cost(unit_cost_cents)
    timestamp_text = format_rfc3339(clock.now())
    line_id = "prl-" + uuid4().hex
    with transaction(conn) as tx:
        request_row = tx.execute(_SELECT_REQUEST_SQL, (purchase_request_id,)).fetchone()
        if request_row is None or request_row["organization_id"] != context.organization_id:
            raise NotFoundError("purchase request not found")
        _editable_request(request_row)
        part_row = tx.execute(_SELECT_PART_SQL, (part_id,)).fetchone()
        if part_row is None or part_row["organization_id"] != context.organization_id:
            raise NotFoundError("part not found")
        if part_row["archived_at"] is not None:
            raise ValidationError("archived parts cannot be added to a purchase request")
        tx.execute(
            "INSERT INTO purchase_request_lines (id, organization_id, purchase_request_id,"
            " part_id, quantity, unit_cost_cents, created_at, updated_at, archived_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            (
                line_id,
                context.organization_id,
                request_row["id"],
                part_id,
                quantity,
                unit_cost_cents,
                timestamp_text,
                timestamp_text,
            ),
        )
        total_cents = request_total_cents(conn, context, purchase_request_id=request_row["id"])
        _apply_edit(
            tx,
            context,
            purchase_request_id=request_row["id"],
            line_id=line_id,
            operation="purchase_request.add_line",
            from_status=request_row["status"],
            total_cents=total_cents,
            expected_version=expected_version,
            timestamp_text=timestamp_text,
            clock=clock,
        )
    return conn.execute(_SELECT_REQUEST_SQL, (request_row["id"],)).fetchone()


def update_request_line(conn, context, *, purchase_request_line_id, quantity, unit_cost_cents, expected_version, clock):
    """Edit one LIVE line of a draft/submitted request; return the request row."""
    require_context(context)
    _validate_quantity(quantity)
    _validate_unit_cost(unit_cost_cents)
    timestamp_text = format_rfc3339(clock.now())
    with transaction(conn) as tx:
        request_row = tx.execute(
            "SELECT pr.* FROM purchase_request_lines prl"
            " JOIN purchase_requests pr ON pr.id = prl.purchase_request_id"
            " AND pr.organization_id = prl.organization_id"
            " WHERE prl.id = ? AND prl.archived_at IS NULL",
            (purchase_request_line_id,),
        ).fetchone()
        if request_row is None or request_row["organization_id"] != context.organization_id:
            raise NotFoundError(LINE_NOT_FOUND_MESSAGE)
        _editable_request(request_row)
        updated = tx.execute(
            "UPDATE purchase_request_lines"
            " SET quantity = ?, unit_cost_cents = ?, updated_at = ?"
            " WHERE id = ? AND organization_id = ? AND archived_at IS NULL",
            (
                quantity,
                unit_cost_cents,
                timestamp_text,
                purchase_request_line_id,
                context.organization_id,
            ),
        ).rowcount
        if updated != 1:
            raise ConflictError(_VERSION_CONFLICT_MESSAGE)
        total_cents = request_total_cents(conn, context, purchase_request_id=request_row["id"])
        _apply_edit(
            tx,
            context,
            purchase_request_id=request_row["id"],
            line_id=purchase_request_line_id,
            operation="purchase_request.edit_line",
            from_status=request_row["status"],
            total_cents=total_cents,
            expected_version=expected_version,
            timestamp_text=timestamp_text,
            clock=clock,
        )
    return conn.execute(_SELECT_REQUEST_SQL, (request_row["id"],)).fetchone()
