"""Purchase-order receipt (T045): stock receipts against an open order.

Business rules live here in the domain service -- never in HTTP
adapters. Recording a receipt rechecks the actor and ownership FIRST,
resolves the idempotency record BEFORE any stale-version or status
rejection, then validates the order state and the lines. Partial
receipts are allowed; over-receipt is rejected. Every accepted receipt
writes the guarded order UPDATE, the receipt INSERT, the receipt line
INSERTs, the balance upserts, the movement INSERTs, the audit records,
and the idempotency completion in ONE explicit transaction
(atomically; sqlite3 errors are mapped as documented). A replayed
operation re-owns the prior receipt and returns it regardless of the
now-stale expected version - the original version was consumed by the
original successful receipt. Unknown and cross-organization ids surface
one canonical message: no existence leak.
"""

from __future__ import annotations

import sqlite3
from uuid import uuid4

from opsledger.core.clock import format_rfc3339
from opsledger.core.context import require_context, require_owned
from opsledger.core.db import transaction
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError
from opsledger.core.idempotency import fail_idempotency
from opsledger.purchasing.idempotency_tx import begin_or_replay, complete_in_tx
from opsledger.purchasing.orders import get_order

__all__ = [
    "OVER_RECEIPT_MESSAGE",
    "ORDER_NOT_OPEN_MESSAGE",
    "receive_order",
    "outstanding_quantity",
]

OVER_RECEIPT_MESSAGE = "receipt quantity exceeds the outstanding order quantity"

ORDER_NOT_OPEN_MESSAGE = "purchase order is not open"

_OPEN_STATUS = "open"

_SELECT_RECEIPT_SQL = "SELECT * FROM receipts WHERE id = ?"
_SELECT_ORDER_LINES_SQL = (
    "SELECT * FROM purchase_order_lines"
    " WHERE purchase_order_id = ? AND organization_id = ?"
    " ORDER BY created_at, id"
)
_SELECT_RECEIVED_SUM_SQL = (
    "SELECT r.organization_id AS organization_id,"
    " COALESCE(SUM(rl.quantity), 0) AS received"
    " FROM receipts r"
    " LEFT JOIN receipt_lines rl ON rl.receipt_id = r.id"
    " AND rl.archived_at IS NULL AND rl.part_id = ?"
    " WHERE r.purchase_order_id = ? AND r.organization_id = ?"
    " AND r.status = 'received'"
)
_SELECT_RECORD_BY_ID_SQL = "SELECT * FROM idempotency_records WHERE id = ?"
_SELECT_PART_SQL = "SELECT * FROM parts WHERE id = ?"
_SELECT_STOCK_LOCATION_SQL = "SELECT * FROM stock_locations WHERE id = ?"
_BALANCE_ID_PREFIX = "stb-"
_MOVEMENT_ID_PREFIX = "stm-"
_INSERT_RECEIPT_SQL = (
    "INSERT INTO receipts (id, organization_id, purchase_order_id,"
    " stock_location_id, received_by, status, created_at, updated_at)"
    " VALUES (?, ?, ?, ?, ?, 'received', ?, ?)"
)
_INSERT_RECEIPT_LINE_SQL = (
    "INSERT INTO receipt_lines (id, organization_id, receipt_id, part_id,"
    " quantity, unit_cost_cents, created_at, archived_at)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, NULL)"
)
_UPDATE_TO_RECEIVED_SQL = (
    "UPDATE purchase_orders SET version = version + 1, updated_at = ?"
    " WHERE id = ? AND status = 'open' AND version = ?"
)
_RECEIPT_ID_PREFIX = "rcp-"
_RECEIPT_LINE_ID_PREFIX = "rcl-"

_VERSION_CONFLICT_MESSAGE = "purchase order version conflict; refresh and retry"
_MISSING_REPLAY_MESSAGE = "replayed receipt is missing"
_DUPLICATE_RECEIPT_MESSAGE = "duplicate receipt for order"


def _received_sum(conn, context, order_id, part_id):
    """Return the received sum for one order/part (live receipt lines only)."""
    row = conn.execute(
        _SELECT_RECEIVED_SUM_SQL, (part_id, order_id, context.organization_id)
    ).fetchone()
    if row is None:
        return 0
    return row["received"]


def _order_lines(conn, context, order_id, part_id):
    """Return the order's live lines for one part, oldest first."""
    return [
        row
        for row in conn.execute(
            _SELECT_ORDER_LINES_SQL, (order_id, context.organization_id)
        ).fetchall()
        if row["part_id"] == part_id
    ]


def _replay_receipt(conn, context, prior_receipt_id):
    """Re-own the prior receipt (require_owned, label receipt)."""
    if not isinstance(prior_receipt_id, str) or not prior_receipt_id:
        raise ConflictError(_MISSING_REPLAY_MESSAGE)
    row = conn.execute(_SELECT_RECEIPT_SQL, (prior_receipt_id,)).fetchone()
    if row is None:
        raise ConflictError(_MISSING_REPLAY_MESSAGE)
    require_owned(context, row, label="receipt")
    return row


def _receive_line(tx, context, *, receipt_id, stock_location_id, line, clock, timestamp_text):
    """Receive one line: line insert, balance upsert, movement insert, audit."""
    part = tx.execute(_SELECT_PART_SQL, (line["part_id"],)).fetchone()
    require_owned(context, part, label="part")
    receipt_line_id = _RECEIPT_LINE_ID_PREFIX + uuid4().hex
    tx.execute(
        _INSERT_RECEIPT_LINE_SQL,
        (
            receipt_line_id,
            context.organization_id,
            receipt_id,
            line["part_id"],
            line["quantity"],
            part["standard_cost_cents"],
            timestamp_text,
        ),
    )
    balance = tx.execute(
        "SELECT * FROM stock_balances WHERE organization_id = ? AND part_id = ?"
        " AND stock_location_id = ?",
        (context.organization_id, line["part_id"], stock_location_id),
    ).fetchone()
    if balance is None:
        balance_id = _BALANCE_ID_PREFIX + uuid4().hex
        tx.execute(
            "INSERT INTO stock_balances (id, organization_id, part_id,"
            " stock_location_id, on_hand, reserved, version, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, 0, 0, 1, ?, ?)",
            (
                balance_id,
                context.organization_id,
                line["part_id"],
                stock_location_id,
                timestamp_text,
                timestamp_text,
            ),
        )
    else:
        balance_id = balance["id"]
    tx.execute(
        "UPDATE stock_balances SET on_hand = on_hand + ?, updated_at = ?"
        " WHERE id = ?",
        (line["quantity"], timestamp_text, balance_id),
    )
    tx.execute(
        "INSERT INTO stock_movements (id, organization_id, part_id,"
        " stock_location_id, operation, on_hand_delta, reserved_delta, reason,"
        " work_order_id, actor_id, created_at)"
        " VALUES (?, ?, ?, ?, 'receive', ?, 0, NULL, NULL, ?, ?)",
        (
            _MOVEMENT_ID_PREFIX + uuid4().hex,
            context.organization_id,
            line["part_id"],
            stock_location_id,
            line["quantity"],
            context.actor_id,
            timestamp_text,
        ),
    )
    from opsledger.audit import record_event_in_tx
    record_event_in_tx(
        tx, context,
        entity_type="receipt",
        entity_id=receipt_id,
        operation="receipt.receive",
        details={
            "receipt_line_id": receipt_line_id,
            "part_id": line["part_id"],
            "quantity": line["quantity"],
        },
        clock=clock,
    )


def outstanding_quantity(conn, context, *, order_id, part_id):
    """Return (ordered, received, outstanding) for one order/part.

    Ordered is the sum of the order's live lines for the part; received
    is the sum of live receipt lines across the order's receipts with
    status 'received'. A part with no live order line is NotFoundError
    ("part not on the purchase order"); the outstanding quantity is
    ordered - received and never below zero (over-receipt is rejected
    upstream).
    """
    require_context(context)
    order = get_order(conn, context, order_id)
    lines = _order_lines(conn, context, order["id"], part_id)
    if not lines:
        raise NotFoundError("part not on the purchase order")
    ordered = sum(row["quantity"] for row in lines)
    received = _received_sum(conn, context, order["id"], part_id)
    return ordered, received, max(0, ordered - received)


def receive_order(conn, context, *, purchase_order_id, stock_location_id, lines, expected_version, actor_id, clock, idempotency_key):
    """Record a stock receipt against an open order, idempotently.

    Returns (receipt_row, idempotency_record, replayed). The idempotency
    record resolves BEFORE any stale-version or status rejection; a
    replay re-owns the prior receipt and returns it regardless of the
    now-stale expected version. Partial receipts are allowed;
    over-receipt is rejected and changes nothing.
    """
    if not isinstance(actor_id, str) or not actor_id.strip():
        raise ValidationError("actor_id must be a non-blank string")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise ValidationError("idempotency_key must be a non-blank string")
    if not isinstance(lines, list) or not lines:
        raise ValidationError("lines must be a non-empty list")
    order_row = get_order(conn, context, purchase_order_id)
    op_payload = {
        "purchase_order_id": purchase_order_id,
        "stock_location_id": stock_location_id,
        "lines": sorted(
            (
                {"part_id": line["part_id"], "quantity": line["quantity"]}
                for line in lines
            ),
            key=lambda line: (line["part_id"], line["quantity"]),
        ),
    }
    record, replay_result = begin_or_replay(
        conn, context,
        operation="purchase.receive_order",
        key=idempotency_key,
        request_payload=op_payload,
        clock=clock,
    )
    if replay_result is not None:
        prior_receipt = _replay_receipt(conn, context, replay_result.get("receipt_id"))
        return prior_receipt, record, True
    if order_row["status"] != _OPEN_STATUS:
        raise ConflictError(ORDER_NOT_OPEN_MESSAGE)
    stock_location = conn.execute(
        _SELECT_STOCK_LOCATION_SQL, (stock_location_id,)
    ).fetchone()
    require_owned(context, stock_location, label="stock location")
    if expected_version != order_row["version"]:
        raise ConflictError(_VERSION_CONFLICT_MESSAGE)
    for line in lines:
        quantity = line.get("quantity")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            fail_idempotency(conn, context, record_id=record["id"], clock=clock)
            raise ValidationError("quantity must be a positive integer")
        lines_for_part = _order_lines(conn, context, order_row["id"], line["part_id"])
        if not lines_for_part:
            fail_idempotency(conn, context, record_id=record["id"], clock=clock)
            raise NotFoundError("part not on the purchase order")
        ordered = sum(row["quantity"] for row in lines_for_part)
        if _received_sum(conn, context, order_row["id"], line["part_id"]) + quantity > ordered:
            fail_idempotency(conn, context, record_id=record["id"], clock=clock)
            raise ConflictError(OVER_RECEIPT_MESSAGE)
    receipt_id = _RECEIPT_ID_PREFIX + uuid4().hex
    timestamp_text = format_rfc3339(clock.now())
    try:
        with transaction(conn) as tx:
            updated = tx.execute(
                _UPDATE_TO_RECEIVED_SQL,
                (timestamp_text, purchase_order_id, expected_version),
            ).rowcount
            if updated != 1:
                raise ConflictError(_VERSION_CONFLICT_MESSAGE)
            tx.execute(
                _INSERT_RECEIPT_SQL,
                (
                    receipt_id,
                    context.organization_id,
                    purchase_order_id,
                    stock_location_id,
                    actor_id,
                    timestamp_text,
                    timestamp_text,
                ),
            )
            for line in lines:
                _receive_line(
                    tx, context,
                    receipt_id=receipt_id,
                    stock_location_id=stock_location_id,
                    line=line,
                    clock=clock,
                    timestamp_text=timestamp_text,
                )
            complete_in_tx(
                tx, context,
                record_id=record["id"],
                result_payload={"receipt_id": receipt_id, "status": "received"},
                clock=clock,
            )
    except sqlite3.IntegrityError as exc:
        fail_idempotency(conn, context, record_id=record["id"], clock=clock)
        raise ConflictError(_DUPLICATE_RECEIPT_MESSAGE) from exc
    return (
        conn.execute(_SELECT_RECEIPT_SQL, (receipt_id,)).fetchone(),
        conn.execute(_SELECT_RECORD_BY_ID_SQL, (record["id"],)).fetchone(),
        False,
    )
