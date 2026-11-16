"""Purchase-order issue (T044): one idempotent order from one approved request.

Business rules live here in the domain service -- never in HTTP
adapters. Issuing ONE order from one approved request rechecks the
actor and ownership FIRST, resolves the idempotency record BEFORE any
stale-version or status rejection, then validates the request state
and mirrors the request's live lines at issue time. Every accepted
issue writes the guarded request UPDATE, the order INSERT, the line
INSERTs, the idempotency completion, and the audit record in ONE
explicit transaction (atomically; sqlite3 errors are mapped as
documented). A replayed operation re-owns the prior order and returns
it regardless of the now-stale expected version - the original version
was consumed by the original successful issue. Unknown and
cross-organization ids surface one canonical message: no existence
leak.
"""

from __future__ import annotations

import sqlite3
from uuid import uuid4

from opsledger.core.clock import format_rfc3339
from opsledger.core.context import require_context, require_owned
from opsledger.core.db import transaction
from opsledger.core.errors import ConflictError, ValidationError
from opsledger.core.idempotency import fail_idempotency
from opsledger.purchasing.idempotency_tx import begin_or_replay, complete_in_tx

__all__ = [
    "REQUEST_NOT_APPROVED_MESSAGE",
    "CANCELLED_REQUEST_MESSAGE",
    "issue_order",
    "get_order",
    "list_order_lines",
]

REQUEST_NOT_APPROVED_MESSAGE = "purchase request is not approved"

CANCELLED_REQUEST_MESSAGE = "cancelled request cannot issue an order"

_APPROVED_STATUS = "approved"
_CANCELLED_STATUS = "cancelled"

_VERSION_CONFLICT_MESSAGE = "purchase request version conflict; refresh and retry"
_MISSING_REPLAY_MESSAGE = "replayed order is missing"
_DUPLICATE_ORDER_MESSAGE = "duplicate purchase order for request"
_NO_LINES_MESSAGE = "purchase request has no lines"
_TOTAL_MISMATCH_MESSAGE = "purchase request total does not match its lines"

_SELECT_ISSUE_SQL = "SELECT * FROM purchase_requests WHERE id = ?"
_SELECT_ORDER_SQL = "SELECT * FROM purchase_orders WHERE id = ?"
_SELECT_ISSUE_LINES_SQL = (
    "SELECT * FROM purchase_request_lines"
    " WHERE purchase_request_id = ? AND organization_id = ?"
    " ORDER BY created_at, id"
)
_SELECT_ORDER_LINES_SQL = (
    "SELECT * FROM purchase_order_lines"
    " WHERE purchase_order_id = ? AND organization_id = ?"
    " ORDER BY created_at, id"
)
_SELECT_RECORD_BY_ID_SQL = "SELECT * FROM idempotency_records WHERE id = ?"
_INSERT_ORDER_SQL = (
    "INSERT INTO purchase_orders (id, organization_id, purchase_request_id,"
    " vendor_id, issued_by, status, total_cents, version, created_at, updated_at,"
    " archived_at) VALUES (?, ?, ?, ?, ?, 'open', ?, 1, ?, ?, NULL)"
)
_INSERT_ORDER_LINE_SQL = (
    "INSERT INTO purchase_order_lines (id, organization_id, purchase_order_id,"
    " part_id, quantity, unit_cost_cents, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
)
_UPDATE_TO_ORDERED_SQL = (
    "UPDATE purchase_requests SET status = 'ordered', version = version + 1,"
    " updated_at = ? WHERE id = ? AND status = 'approved' AND version = ?"
)
_ORDER_ID_PREFIX = "por-"
_ORDER_LINE_ID_PREFIX = "pol-"


def _replay_order(
    conn: object,
    context: object,
    order_id: object,
) -> object:
    """Re-own the prior order (require_owned, label purchase order)."""
    if not isinstance(order_id, str) or not order_id:
        raise ConflictError(_MISSING_REPLAY_MESSAGE)
    row = conn.execute(_SELECT_ORDER_SQL, (order_id,)).fetchone()
    if row is None:
        raise ConflictError(_MISSING_REPLAY_MESSAGE)
    require_owned(context, row, label="purchase order")
    return row


def _ordered_request(
    conn: object,
    context: object,
    purchase_request_id: object,
) -> object:
    """Fetch the request row; ownership first (require_owned, label purchase request)."""
    require_context(context)
    row = conn.execute(_SELECT_ISSUE_SQL, (purchase_request_id,)).fetchone()
    require_owned(context, row, label="purchase request")
    return row


def issue_order(conn, context, *, purchase_request_id, expected_version, actor_id, clock, idempotency_key):
    """Issue one order from an approved request, idempotently.

    Returns (order_row, idempotency_record, replayed). The idempotency
    record resolves BEFORE any stale-version or status rejection; a
    replay re-owns the prior order and returns it regardless of the
    now-stale expected version.
    """
    if not isinstance(actor_id, str) or not actor_id:
        raise ValidationError("actor_id must be a non-blank string")
    if not isinstance(idempotency_key, str) or not idempotency_key:
        raise ValidationError("idempotency_key must be a non-blank string")
    request_row = _ordered_request(conn, context, purchase_request_id)
    op_payload = {"purchase_request_id": request_row["id"]}
    record, replay_result = begin_or_replay(
        conn, context,
        operation="purchase.issue_order",
        key=idempotency_key,
        request_payload=op_payload,
        clock=clock,
    )
    if replay_result is not None:
        prior_order = _replay_order(conn, context, replay_result.get("order_id"))
        return prior_order, record, True
    current_status = request_row["status"]
    if current_status == _CANCELLED_STATUS:
        raise ConflictError(CANCELLED_REQUEST_MESSAGE)
    if current_status != _APPROVED_STATUS:
        raise ConflictError(REQUEST_NOT_APPROVED_MESSAGE)
    if expected_version != request_row["version"]:
        raise ConflictError(_VERSION_CONFLICT_MESSAGE)
    line_rows = [
        line
        for line in conn.execute(
            _SELECT_ISSUE_LINES_SQL, (request_row["id"], context.organization_id)
        ).fetchall()
        if line["archived_at"] is None
    ]
    if not line_rows:
        raise ValidationError(_NO_LINES_MESSAGE)
    total_cents = sum(line["quantity"] * line["unit_cost_cents"] for line in line_rows)
    if total_cents != request_row["total_cents"]:
        raise ConflictError(_TOTAL_MISMATCH_MESSAGE)
    return _issue_issue(
        conn, context,
        request_row=request_row,
        line_rows=line_rows,
        expected_version=expected_version,
        actor_id=actor_id,
        clock=clock,
        record_id=record["id"],
    )


def _issue_issue(conn, context, *, request_row, line_rows, expected_version, actor_id, clock, record_id):
    """Write the issue in ONE explicit transaction (all steps, atomically)."""
    order_id = _ORDER_ID_PREFIX + uuid4().hex
    timestamp_text = format_rfc3339(clock.now())
    try:
        with transaction(conn) as tx:
            updated = tx.execute(
                _UPDATE_TO_ORDERED_SQL,
                (timestamp_text, request_row["id"], expected_version),
            ).rowcount
            if updated != 1:
                raise ConflictError(_VERSION_CONFLICT_MESSAGE)
            tx.execute(
                _INSERT_ORDER_SQL,
                (
                    order_id,
                    context.organization_id,
                    request_row["id"],
                    request_row["vendor_id"],
                    actor_id,
                    request_row["total_cents"],
                    timestamp_text,
                    timestamp_text,
                ),
            )
            for line in line_rows:
                tx.execute(
                    _INSERT_ORDER_LINE_SQL,
                    (
                        _ORDER_LINE_ID_PREFIX + uuid4().hex,
                        context.organization_id,
                        order_id,
                        line["part_id"],
                        line["quantity"],
                        line["unit_cost_cents"],
                        timestamp_text,
                    ),
                )
            complete_in_tx(
                tx, context,
                record_id=record_id,
                result_payload={
                    "order_id": order_id,
                    "status": "open",
                    "total_cents": request_row["total_cents"],
                },
                clock=clock,
            )
            from opsledger.audit import record_event_in_tx
            record_event_in_tx(
                tx, context,
                entity_type="purchase_order",
                entity_id=order_id,
                operation="purchase_order.issue",
                details={
                    "purchase_request_id": request_row["id"],
                    "from_version": expected_version,
                    "to_version": expected_version + 1,
                    "total_cents": request_row["total_cents"],
                },
                clock=clock,
            )
    except sqlite3.IntegrityError as exc:
        fail_idempotency(conn, context, record_id=record_id, clock=clock)
        raise ConflictError(_DUPLICATE_ORDER_MESSAGE) from exc
    return (
        conn.execute(_SELECT_ORDER_SQL, (order_id,)).fetchone(),
        conn.execute(_SELECT_RECORD_BY_ID_SQL, (record_id,)).fetchone(),
        False,
    )


def get_order(conn, context, purchase_order_id):
    """Return one owned order row; unknown and cross-org ids are the same error."""
    row = conn.execute(_SELECT_ORDER_SQL, (purchase_order_id,)).fetchone()
    require_owned(context, row, label="purchase order")
    return row


def list_order_lines(conn, context, *, purchase_order_id):
    """List one order's lines (oldest first, in scope)."""
    get_order(conn, context, purchase_order_id)
    return [
        row
        for row in conn.execute(
            _SELECT_ORDER_LINES_SQL, (purchase_order_id, context.organization_id)
        ).fetchall()
    ]
