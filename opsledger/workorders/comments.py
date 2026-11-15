"""Work-order comment service for OpsLedger (T030, M4).

Spec M4/T030 acceptance: user text is literal (stored verbatim, never
interpreted — spreadsheet formula prefixes like ``=`` or ``@`` are data,
not commands); the author identity is derived from the caller-provided
context, not from request bodies. Every comment anchors to the work
order's aggregate version at write time (version-aware history); comments
are immutable: no update or delete paths exist.
"""

from __future__ import annotations

import sqlite3
from uuid import uuid4

from opsledger.core.clock import Clock, format_rfc3339
from opsledger.core.context import require_context, require_owned
from opsledger.core.db import transaction
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError

__all__ = [
    "BODY_MESSAGE",
    "add_comment",
    "list_comments",
]

BODY_MESSAGE = "comment body must be a non-empty string"


def add_comment(conn, context, *, work_order_id, author_id, body, clock):
    """Add one comment with the work order's current version (literal body)."""
    require_context(context)
    if not isinstance(body, str) or not body.strip():
        raise ValidationError(BODY_MESSAGE)
    work_order = conn.execute("SELECT * FROM work_orders WHERE id = ?", (work_order_id,)).fetchone()
    require_owned(context, work_order, label="work order")
    comment_id = "cmt-" + uuid4().hex
    timestamp_text = format_rfc3339(clock.now())
    try:
        with transaction(conn) as tx:
            tx.execute(
                "INSERT INTO comments (id, organization_id, work_order_id, author_id, body, at_version, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (comment_id, context.organization_id, work_order["id"], author_id, body, work_order["version"], timestamp_text),
            )
    except sqlite3.IntegrityError as exc:
        raise ConflictError("unknown work order for comment") from exc
    return conn.execute(
        "SELECT * FROM comments WHERE id = ?", (comment_id,),
    ).fetchone()


def list_comments(conn, context, *, work_order_id):
    """List one work order's comments in creation order (immutable history)."""
    require_context(context)
    return conn.execute(
        "SELECT * FROM comments"
        " WHERE organization_id = ? AND work_order_id = ?"
        " ORDER BY created_at, id",
        (context.organization_id, work_order_id),
    ).fetchall()
