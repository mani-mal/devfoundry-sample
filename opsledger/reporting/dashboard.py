"""READ-ONLY dashboard aggregation for OpsLedger (T057).

A READ-ONLY dashboard over already-stored business data: no mutating
statement of any kind. Every SELECT is org-scoped via
:func:`opsledger.core.context.scoped_all` (or a parameterized query with
organization_id in the WHERE clause when a scalar is read). Totals come
from STORED data only. Cost is integer cents only.
"""

from __future__ import annotations

from opsledger.core.context import require_context, scoped_all
from opsledger.identity.permissions import require_permission
from opsledger.workorders.orders import WORK_ORDER_STATUSES

__all__ = ["dashboard"]


def _count_work_orders(conn, context) -> int:
    """Count every work order of the organization, archived or not."""
    rows = scoped_all(
        conn,
        context,
        "SELECT organization_id FROM work_orders WHERE organization_id = ?",
        (context.organization_id,),
    )
    return len(rows)


def _stock_totals(conn, context) -> dict:
    """Return stored on-hand/reserved sums over stock_balances."""
    row = scoped_all(
        conn,
        context,
        "SELECT organization_id, COALESCE(SUM(on_hand), 0) AS on_hand,"
        " COALESCE(SUM(reserved), 0) AS reserved FROM stock_balances"
        " WHERE organization_id = ?",
        (context.organization_id,),
    )
    if not row:
        return {"on_hand": 0, "reserved": 0}
    return {"on_hand": row[0]["on_hand"], "reserved": row[0]["reserved"]}


def _asset_count(conn, context) -> int:
    """Count every asset of the organization, archived or not."""
    rows = scoped_all(
        conn,
        context,
        "SELECT organization_id FROM assets WHERE organization_id = ?",
        (context.organization_id,),
    )
    return len(rows)


def _scalar_sum(query_sql: str, conn, context) -> int:
    """Return one parameterized scalar SUM, 0 when the row is missing."""
    require_context(context)
    row = conn.execute(query_sql, (context.organization_id,)).fetchone()
    if row is None:
        return 0
    return int(row[0] or 0)


def dashboard(conn, context, *, actor) -> dict:
    """Return the READ-ONLY in-scope dashboard totals as one dict."""
    require_permission(actor, "reporting.read")
    by_status = {}
    status_rows = scoped_all(
        conn,
        context,
        "SELECT organization_id, status, COUNT(*) AS n FROM work_orders"
        " WHERE organization_id = ? GROUP BY status",
        (context.organization_id,),
    )
    counts = {row["status"]: row["n"] for row in status_rows}
    for status in WORK_ORDER_STATUSES:
        by_status[status] = counts.get(status, 0)
    labor_row = _scalar_sum(
        "SELECT COALESCE(SUM(cost_cents), 0) FROM labor_entries"
        " WHERE organization_id = ?",
        conn,
        context,
    )
    return {
        "work_orders": {"total": _count_work_orders(conn, context), "by_status": by_status},
        "assets": {"total": _asset_count(conn, context)},
        "stock": _stock_totals(conn, context),
        "labor_cost_cents": labor_row,
    }
