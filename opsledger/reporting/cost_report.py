"""READ-ONLY per-asset cost report for OpsLedger (T058, M8).

A READ-ONLY report over already-stored business data: labor-entry cost
plus consumed-part cost per asset. No mutating statement of any kind.
Every SELECT is org-scoped via :func:`opsledger.core.context.scoped_all`
(a parameterized query with organization_id in the WHERE clause when a
scalar is read). Cost is integer cents only; totals come from STORED
data only.
"""

from __future__ import annotations

from opsledger.core.context import require_context, scoped_all
from opsledger.identity.permissions import require_permission

__all__ = ["asset_cost_report"]


def _asset_rows(conn, context) -> list[dict]:
    """Return one raw stored row per asset of the organization, in stable order."""
    return scoped_all(
        conn,
        context,
        "SELECT a.organization_id, a.id AS asset_id, a.tag, a.name,"
        " COALESCE(l.total, 0) AS labor,"
        " COALESCE(c.total, 0) AS consumed"
        " FROM assets a"
        " LEFT JOIN ("
        "  SELECT wo.asset_id AS asset_id, SUM(le.cost_cents) AS total"
        "  FROM labor_entries le"
        "  JOIN work_orders wo ON wo.id = le.work_order_id"
        "  WHERE wo.organization_id = ?"
        "  GROUP BY wo.asset_id"
        " ) l ON l.asset_id = a.id"
        " LEFT JOIN ("
        "  SELECT wo2.asset_id AS asset_id,"
        "  SUM(-mv.on_hand_delta * p.standard_cost_cents) AS total"
        "  FROM stock_movements mv"
        "  JOIN parts p ON p.id = mv.part_id"
        "  JOIN work_orders wo2 ON wo2.id = mv.work_order_id"
        "  WHERE mv.operation = 'consume' AND wo2.organization_id = ?"
        "  GROUP BY wo2.asset_id"
        " ) c ON c.asset_id = a.id"
        " WHERE a.organization_id = ?"
        " ORDER BY a.created_at, a.id",
        (context.organization_id, context.organization_id, context.organization_id),
    )


def _labor_and_consumption(raw: dict) -> dict:
    """Project one raw stored row into the public cost-report shape."""
    return {
        "asset_id": raw["asset_id"],
        "tag": raw["tag"],
        "name": raw["name"],
        "labor_cost_cents": int(raw["labor"]),
        "consumed_part_cost_cents": int(raw["consumed"]),
        "total_cost_cents": int(raw["labor"]) + int(raw["consumed"]),
    }


def asset_cost_report(conn, context, *, actor) -> list[dict]:
    """Return the READ-ONLY per-asset cost report (labor + consumed parts)."""
    require_permission(actor, "reporting.read")
    return [_labor_and_consumption(raw) for raw in _asset_rows(conn, context)]
