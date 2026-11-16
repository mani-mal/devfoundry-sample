"""READ-ONLY cross-module search for OpsLedger (T059).

A READ-ONLY authorized search over already-stored business data across
three entity kinds: assets, work orders and parts. No mutating statement
of any kind. Every SELECT is org-scoped with
``organization_id = context.organization_id`` in its WHERE clause and
:func:`opsledger.core.context.require_context` re-verifies the context.

Matching rule: the user query is a case-insensitive substring match
(SQLite LIKE over LOWER-ed operands, kept consistent everywhere). The
LIKE wildcards ``%`` and ``_`` are LITERAL in the user query: the
pattern is escaped with the backslash escape character ``\\`` and every
LIKE operand carries ``ESCAPE '\\'`` in the SQL, so a query of ``100%``
matches only strings containing a literal percent sign and never ``100x``.
Results are ordered by ``created_at, id`` and capped at 20 matches per
entity kind.
"""

from __future__ import annotations

from opsledger.core.context import require_context
from opsledger.core.errors import ValidationError
from opsledger.identity.permissions import require_permission

__all__ = ["search"]

_MATCH_LIMIT = 20


def _like(value: str) -> str:
    """Escape LIKE wildcards so the query matches literally."""
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def search(conn, context, *, actor, query) -> dict:
    """Return the READ-ONLY cross-module matches for the query as one dict."""
    require_permission(actor, "reporting.read")
    require_context(context)
    if not isinstance(query, str):
        raise ValidationError("query must be a non-empty string")
    query = query.strip()
    if not query:
        raise ValidationError("query must be a non-empty string")
    pattern = _like(query)
    result = {"query": query}

    asset_rows = conn.execute(
        "SELECT id, tag, name FROM assets"
        " WHERE organization_id = ?"
        " AND (LOWER(tag) LIKE ? ESCAPE '\\'"
        " OR LOWER(name) LIKE ? ESCAPE '\\')"
        " ORDER BY created_at, id LIMIT ?",
        (context.organization_id, pattern, pattern, _MATCH_LIMIT),
    ).fetchall()
    result["assets"] = [{"id": r["id"], "tag": r["tag"], "name": r["name"]} for r in asset_rows]

    work_order_rows = conn.execute(
        "SELECT id, number, title, status FROM work_orders"
        " WHERE organization_id = ?"
        " AND (LOWER(number) LIKE ? ESCAPE '\\'"
        " OR LOWER(title) LIKE ? ESCAPE '\\')"
        " ORDER BY created_at, id LIMIT ?",
        (context.organization_id, pattern, pattern, _MATCH_LIMIT),
    ).fetchall()
    result["work_orders"] = [
        {"id": r["id"], "number": r["number"], "title": r["title"], "status": r["status"]}
        for r in work_order_rows
    ]

    part_rows = conn.execute(
        "SELECT id, sku, name FROM parts"
        " WHERE organization_id = ?"
        " AND (LOWER(sku) LIKE ? ESCAPE '\\'"
        " OR LOWER(name) LIKE ? ESCAPE '\\')"
        " ORDER BY created_at, id LIMIT ?",
        (context.organization_id, pattern, pattern, _MATCH_LIMIT),
    ).fetchall()
    result["parts"] = [{"id": r["id"], "sku": r["sku"], "name": r["name"]} for r in part_rows]
    return result
