"""READ-ONLY bounded CSV export of work orders for OpsLedger (T060).

A READ-ONLY authorized export of already-stored work-order data. No
mutating statement of any kind. Every row comes from one org-scoped
SELECT with
``organization_id = context.organization_id`` in its WHERE clause and
:func:`opsledger.core.context.require_context` re-verifies the context.

Rows are rendered with the stdlib :mod:`csv` module (RFC 4180 quoting,
``\\r\\n`` line terminators). Cell text is DATA, never markup: a text
cell whose text starts with ``=``, ``+``, ``-`` or ``@`` is prefixed
with a single apostrophe so spreadsheet applications do not evaluate
it (formula injection). The apostrophe is added to the rendered cell
only; the header row is never prefixed.

The export is bounded: at most 1000 data rows are exported, the first
1000 in the stable ``created_at, id`` order. An organization with more
work orders simply gets the first 1000; no error and no truncation
marker. The function returns the CSV text (a ``str``); it never writes
files and never touches the network.
"""

from __future__ import annotations

import csv
import io

from opsledger.core.context import require_context
from opsledger.identity.permissions import require_permission

__all__ = ["CSV_HEADER", "export_work_orders"]

_ROW_LIMIT = 1000
_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _csv_escape(cell: str) -> str:
    """Prefix formula-injection-looking cell text with one apostrophe."""
    if cell.startswith(_FORMULA_PREFIXES):
        return "'" + cell
    return cell


CSV_HEADER = [
    "work_order_id",
    "number",
    "title",
    "status",
    "priority",
    "asset_id",
    "created_at",
]


def export_work_orders(conn, context, *, actor) -> str:
    """Return the READ-ONLY CSV export of in-scope work orders as one str."""
    require_permission(actor, "export.read")
    require_context(context)
    rows = conn.execute(
        "SELECT id, number, title, status, priority, asset_id, created_at"
        " FROM work_orders"
        " WHERE organization_id = ?"
        " ORDER BY created_at, id"
        " LIMIT ?",
        (context.organization_id, _ROW_LIMIT),
    ).fetchall()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_HEADER)
    for row in rows:
        writer.writerow(
            [
                _csv_escape(str(row["id"])),
                _csv_escape(str(row["number"])),
                _csv_escape(str(row["title"])),
                str(row["status"]),
                str(row["priority"]),
                str(row["asset_id"]),
                str(row["created_at"]),
            ]
        )
    return buffer.getvalue()
