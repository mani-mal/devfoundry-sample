"""Read-only purchasing export view for OpsLedger (T048).

A READ-ONLY export over purchasing data: no UPDATE, no DELETE. Every
scoped SELECT surfaces organization_id directly (a JOIN SELECT that
does not surface organization_id cannot be scoped by
:func:`opsledger.core.context.scoped_all`). Every lookup carries the
authenticated organization context; an unknown order and a
cross-organization order raise the same owned-lookup NotFoundError
(require_owned, label "purchase order"), no leak. Cost is integer
cents only.
"""

from __future__ import annotations

from opsledger.core.context import scoped_all
from opsledger.purchasing.orders import get_order

__all__ = [
    "receipt_history",
    "order_outstanding",
    "export_purchasing",
]

_RECEIPTS_SQL = (
    "SELECT * FROM receipts WHERE purchase_order_id = ?"
    " AND organization_id = ? ORDER BY created_at, id"
)
_LINES_SQL = (
    "SELECT rl.organization_id, rl.* FROM receipt_lines rl"
    " JOIN receipts r ON r.id = rl.receipt_id"
    " WHERE rl.receipt_id = ? AND r.organization_id = ?"
    " AND r.status = 'received'"
    " ORDER BY rl.created_at, rl.id"
)


def _as_dict(row):
    return dict(row)


def receipt_history(conn, context, *, purchase_order_id):
    """Return one dict per receipt of the owned order, oldest first."""
    receipt_rows = get_order(conn, context, purchase_order_id)
    receipts = []
    for receipt in scoped_all(
        conn, context, _RECEIPTS_SQL, (receipt_rows["id"], context.organization_id)
    ):
        lines = scoped_all(
            conn, context, _LINES_SQL, (receipt["id"], context.organization_id)
        )
        cost_cents = sum(
            line["unit_cost_cents"] * line["quantity"] for line in lines
        )
        receipts.append(
            {
                "receipt": _as_dict(receipt),
                "lines": [_as_dict(line) for line in lines],
                "cost_cents": cost_cents,
            }
        )
    return receipts


_ORDER_LINES_SQL = (
    "SELECT * FROM purchase_order_lines"
    " WHERE purchase_order_id = ? AND organization_id = ?"
    " ORDER BY created_at, id"
)
_RECEIPT_LINES_SQL = (
    "SELECT r.organization_id AS organization_id, rl.* FROM receipt_lines rl"
    " JOIN receipts r ON r.id = rl.receipt_id"
    " WHERE r.purchase_order_id = ? AND r.organization_id = ?"
    " AND r.status = 'received' AND rl.archived_at IS NULL"
    " ORDER BY rl.created_at, rl.id"
)
_VENDOR_ROWS_SQL = "SELECT * FROM vendors WHERE organization_id = ? ORDER BY created_at, id"
_REQUEST_ROWS_SQL = "SELECT * FROM purchase_requests WHERE organization_id = ? ORDER BY created_at, id"
_REQUEST_APPROVALS_SQL = (
    "SELECT * FROM approvals"
    " WHERE purchase_request_id = ? AND organization_id = ?"
    " ORDER BY decided_at, id"
)
_ORDER_ROWS_SQL = "SELECT * FROM purchase_orders WHERE organization_id = ? ORDER BY created_at, id"


def _part_lines(lines, part_id):
    return [line for line in lines if line["part_id"] == part_id]


def order_outstanding(conn, context, *, purchase_order_id):
    """Return one per-line dict over the owned order's live lines."""
    receipt_row = get_order(conn, context, purchase_order_id)
    line_rows = scoped_all(
        conn, context, _ORDER_LINES_SQL, (receipt_row["id"], context.organization_id)
    )
    receipt_lines = scoped_all(
        conn, context, _RECEIPT_LINES_SQL, (purchase_order_id, context.organization_id)
    )
    outstanding = []
    for line in line_rows:
        part_id = line["part_id"]
        received = sum(row["quantity"] for row in _part_lines(receipt_lines, part_id))
        ordered = line["quantity"]
        outstanding.append(
            {
                "part_id": part_id,
                "ordered": ordered,
                "received": received,
                "outstanding": ordered - received,
                "unit_cost_cents": line["unit_cost_cents"],
            }
        )
    return outstanding


def export_purchasing(conn, context):
    """Return the full in-scope purchasing export as one JSON-serializable dict."""
    vendors = []
    for vendor in scoped_all(
        conn, context, _VENDOR_ROWS_SQL, (context.organization_id,)
    ):
        vendors.append(_as_dict(vendor))
    requests = []
    for request in scoped_all(
        conn, context, _REQUEST_ROWS_SQL, (context.organization_id,)
    ):
        approvals = [
            _as_dict(approval)
            for approval in scoped_all(
                conn, context, _REQUEST_APPROVALS_SQL, (request["id"], context.organization_id)
            )
        ]
        request_row = _as_dict(request)
        request_row["approvals"] = approvals
        requests.append(request_row)
    orders = []
    for order in scoped_all(
        conn, context, _ORDER_ROWS_SQL, (context.organization_id,)
    ):
        orders.append(
            {
                "order": _as_dict(order),
                "outstanding": order_outstanding(conn, context, purchase_order_id=order["id"]),
                "receipts": receipt_history(conn, context, purchase_order_id=order["id"]),
            }
        )
    return {
        "vendors": vendors,
        "purchase_requests": requests,
        "purchase_orders": orders,
    }
