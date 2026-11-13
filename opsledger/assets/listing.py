"""Asset filtered list with stable pagination (T019, M3).

Stable pagination rule (spec M3/T019): results are ordered by
``created_at ASC, id ASC`` -- a deterministic total order. The ``id``
tiebreaker keeps assets with identical ``created_at`` timestamps in the
same position on every page, so identical timestamps neither duplicate
nor omit stable rows. Paging is keyset-only: a cursor of
``(after_created_at, after_id)`` re-entered as WHERE predicates
(``created_at > ? OR (created_at = ? AND id > ?)``). OFFSET is never
used: an offset duplicates or omits rows when equal timestamps reorder
between pages or records are inserted concurrently. All clauses are
fixed fragments and every value is a bound parameter; the organization
filter is part of the WHERE and :func:`opsledger.core.context.scoped_all`
re-verifies each row is in scope (defense in depth).
"""

from __future__ import annotations

import sqlite3

from opsledger.core.context import (
    OrganizationContext,
    require_context,
    scoped_all,
)
from opsledger.core.errors import ValidationError
from opsledger.assets.assets import CRITICALITIES

__all__ = [
    "list_assets",
    "asset_page_cursor",
]

_MIN_LIMIT = 1
_MAX_LIMIT = 200

_LIMIT_MESSAGE = "limit must be between 1 and 200"
_CRITICALITY_MESSAGE = "criticality must be one of: low, medium, high"
_CURSOR_MISMATCH_MESSAGE = "cursor requires both after_created_at and after_id"


def list_assets(
    conn: sqlite3.Connection,
    context: object,
    *,
    site_id: str | None = None,
    criticality: str | None = None,
    include_archived: bool = False,
    limit: int = 50,
    after_created_at: str | None = None,
    after_id: str | None = None,
) -> list[sqlite3.Row]:
    """Select the organization's assets matching the filters, in stable order.

    require_context(context); limit must be an int with 1 <= limit <= 200
    (ValidationError "limit must be between 1 and 200" otherwise); when
    criticality is not None it must be one of the values in
    :data:`opsledger.assets.assets.CRITICALITIES` (ValidationError otherwise).
    The WHERE is assembled dynamically from FIXED clause fragments --
    organization_id = ? is always present, site_id and criticality are added
    when given, archived_at IS NULL filters out archived rows unless
    include_archived is True, and the keyset clause
    (created_at > ? OR (created_at = ? AND id > ?)) is added when the cursor
    is given (both parts together, else ValidationError). ORDER BY
    created_at ASC, id ASC LIMIT ? with every value a bound parameter.
    Executed once via scoped_all(conn, context, sql, params), which keeps
    only rows in the caller's organization in order (defense in depth);
    the list of rows is returned.
    """
    required_context = require_context(context)
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValidationError(_LIMIT_MESSAGE)
    if not (_MIN_LIMIT <= limit <= _MAX_LIMIT):
        raise ValidationError(_LIMIT_MESSAGE)
    if criticality is not None and criticality not in CRITICALITIES:
        raise ValidationError(_CRITICALITY_MESSAGE)
    if (after_created_at is None) != (after_id is None):
        raise ValidationError(_CURSOR_MISMATCH_MESSAGE)

    clauses = ["organization_id = ?"]
    params: list[object] = [required_context.organization_id]
    if site_id is not None:
        clauses.append("AND site_id = ?")
        params.append(site_id)
    if criticality is not None:
        clauses.append("AND criticality = ?")
        params.append(criticality)
    if not include_archived:
        clauses.append("AND archived_at IS NULL")
    if after_created_at is not None:
        clauses.append("AND (created_at > ? OR (created_at = ? AND id > ?))")
        params.append(after_created_at)
        params.append(after_created_at)
        params.append(after_id)

    sql = (
        "SELECT id, organization_id, site_id, tag, name, criticality,"
        " purchase_cost_cents, version, created_at, updated_at, archived_at"
        " FROM assets WHERE " + " ".join(clauses) + " ORDER BY created_at ASC, id ASC LIMIT ?"
    )
    params.append(limit)
    return scoped_all(conn, context, sql, tuple(params))


def asset_page_cursor(row: sqlite3.Row) -> dict[str, str]:
    """Return the next-page cursor ({after_created_at, after_id}) for a row.

    The caller passes both values back to list_assets; this makes the
    keyset contract explicit and testable.
    """
    return {"after_created_at": row["created_at"], "after_id": row["id"]}
