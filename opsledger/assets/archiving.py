"""Site/asset archive domain module for OpsLedger: archive/unarchive (T021, M3).

Scoping rule (spec M3/T021): archive sets ``archived_at`` (never DELETE —
referenced records are retained) and unarchive clears it. Archived sites
and assets are excluded from the default lists (list_sites/list_assets
filter archived unless include_archived is True). A SITE archive is
refused with the one canonical message :data:`SITE_HAS_LIVE_ASSETS_MESSAGE`
while any asset on the site is not archived — an archived site with live
assets would strand them; the assets are retained, never deleted. Archived
objects cannot accept new work: no asset can be created on an archived site
(guard :func:`require_site_accepts_assets`, message :data:`ARCHIVED_SITE_MESSAGE`).
Archiving an ASSET is always allowed in this baseline: no open-work guard for
assets exists yet (work orders are M4).
"""

from __future__ import annotations

import sqlite3

from opsledger.core.clock import Clock, format_rfc3339
from opsledger.core.db import transaction
from opsledger.core.context import (
    OrganizationContext,
    require_context,
    require_owned,
)
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError

__all__ = [
    "SITE_HAS_LIVE_ASSETS_MESSAGE",
    "ARCHIVED_SITE_MESSAGE",
    "archive_site",
    "archive_asset",
    "unarchive_site",
    "unarchive_asset",
    "require_site_accepts_assets",
]

SITE_HAS_LIVE_ASSETS_MESSAGE = (
    "site has assets that are not archived; archive them first"
)

ARCHIVED_SITE_MESSAGE = "site is archived"

_SELECT_SITE_BY_ID_SQL = (
    "SELECT id, organization_id, code, name, timezone, created_at, archived_at"
    " FROM sites WHERE id = ?"
)

_SELECT_ASSET_BY_ID_SQL = (
    "SELECT id, organization_id, site_id, tag, name, criticality,"
    " purchase_cost_cents, version, created_at, updated_at, archived_at"
    " FROM assets WHERE id = ?"
)

_COUNT_LIVE_ASSETS_SQL = (
    "SELECT COUNT(*) FROM assets WHERE site_id = ? AND archived_at IS NULL"
)

_ARCHIVE_SITE_SQL = "UPDATE sites SET archived_at = ? WHERE id = ?"

_UNARCHIVE_SITE_SQL = "UPDATE sites SET archived_at = NULL WHERE id = ?"

_ARCHIVE_ASSET_SQL = "UPDATE assets SET archived_at = ? WHERE id = ?"

_UNARCHIVE_ASSET_SQL = "UPDATE assets SET archived_at = NULL WHERE id = ?"


def archive_site(
    conn: sqlite3.Connection,
    context: object,
    *,
    site_id: str,
    clock: Clock,
) -> sqlite3.Row:
    """Archive one owned site: set archived_at (never DELETE).

    require_context(context); SELECT the site row by id and guard it with
    require_owned(label "site"). GUARD: SELECT COUNT(*) FROM assets WHERE
    site_id = ? AND archived_at IS NULL — when the count is > 0 raise
    ConflictError with SITE_HAS_LIVE_ASSETS_MESSAGE (referenced/live
    records block the archive; they are retained, never deleted); otherwise
    UPDATE sites SET archived_at = ? WHERE id = ? in one transaction(conn)
    with the timestamp serialized canonically via format_rfc3339(clock.now()).
    Idempotent: when archived_at is already set, return the row unchanged,
    never raise. Re-SELECT and return the archived row.
    """
    require_context(context)
    row = conn.execute(_SELECT_SITE_BY_ID_SQL, (site_id,)).fetchone()
    require_owned(context, row, label="site")
    if row["archived_at"] is not None:
        return row
    timestamp_text = format_rfc3339(clock.now())
    with transaction(conn) as tx:
        count = tx.execute(_COUNT_LIVE_ASSETS_SQL, (site_id,)).fetchone()[0]
        if count > 0:
            raise ConflictError(SITE_HAS_LIVE_ASSETS_MESSAGE)
        tx.execute(_ARCHIVE_SITE_SQL, (timestamp_text, site_id))
    updated = conn.execute(_SELECT_SITE_BY_ID_SQL, (site_id,)).fetchone()
    require_owned(context, updated, label="site")
    return updated


def archive_asset(
    conn: sqlite3.Connection,
    context: object,
    *,
    asset_id: str,
    clock: Clock,
) -> sqlite3.Row:
    """Archive one owned asset: set archived_at (never DELETE).

    require_context(context); SELECT the asset row by id and guard it with
    require_owned(label "asset"). UPDATE assets SET archived_at = ? WHERE
    id = ? in one transaction(conn) with the timestamp serialized canonically
    via format_rfc3339(clock.now()). Idempotent: when archived_at is already
    set, return the row unchanged, never raise. Re-SELECT and return the
    archived row. NO OPEN-WORK GUARD EXISTS YET: work orders are M4, so
    archiving an asset is always allowed in this baseline.
    """
    require_context(context)
    row = conn.execute(_SELECT_ASSET_BY_ID_SQL, (asset_id,)).fetchone()
    require_owned(context, row, label="asset")
    if row["archived_at"] is not None:
        return row
    timestamp_text = format_rfc3339(clock.now())
    with transaction(conn) as tx:
        tx.execute(_ARCHIVE_ASSET_SQL, (timestamp_text, asset_id))
    updated = conn.execute(_SELECT_ASSET_BY_ID_SQL, (asset_id,)).fetchone()
    require_owned(context, updated, label="asset")
    return updated


def unarchive_site(
    conn: sqlite3.Connection,
    context: object,
    *,
    site_id: str,
    clock: Clock,
) -> sqlite3.Row:
    """Unarchive one owned site: clear archived_at (records are retained).

    require_context(context); SELECT the site row by id and guard it with
    require_owned(label "site"). UPDATE sites SET archived_at = NULL WHERE
    id = ? in one transaction(conn); re-select and return the updated row,
    re-guarded. The clock parameter is accepted for symmetry with the
    archive flows — it is not serialized anywhere.
    """
    require_context(context)
    row = conn.execute(_SELECT_SITE_BY_ID_SQL, (site_id,)).fetchone()
    require_owned(context, row, label="site")
    with transaction(conn) as tx:
        tx.execute(_UNARCHIVE_SITE_SQL, (site_id,))
    updated = conn.execute(_SELECT_SITE_BY_ID_SQL, (site_id,)).fetchone()
    require_owned(context, updated, label="site")
    return updated


def unarchive_asset(
    conn: sqlite3.Connection,
    context: object,
    *,
    asset_id: str,
    clock: Clock,
) -> sqlite3.Row:
    """Unarchive one owned asset: clear archived_at (records are retained).

    require_context(context); SELECT the asset row by id and guard it with
    require_owned(label "asset"). UPDATE assets SET archived_at = NULL WHERE
    id = ? in one transaction(conn); re-select and return the updated row,
    re-guarded. The clock parameter is accepted for symmetry with the
    archive flows — it is not serialized anywhere.
    """
    require_context(context)
    row = conn.execute(_SELECT_ASSET_BY_ID_SQL, (asset_id,)).fetchone()
    require_owned(context, row, label="asset")
    with transaction(conn) as tx:
        tx.execute(_UNARCHIVE_ASSET_SQL, (asset_id,))
    updated = conn.execute(_SELECT_ASSET_BY_ID_SQL, (asset_id,)).fetchone()
    require_owned(context, updated, label="asset")
    return updated


def require_site_accepts_assets(site_row: object) -> None:
    """Refuse assets on an archived site (defensive read).

    The guard used by later create flows: raise ConflictError with
    ARCHIVED_SITE_MESSAGE when site_row["archived_at"] is not None (read
    defensively — dict or Row both work); pass silently when the site is
    live; ValidationError for a non-row-like object without the field.
    """
    try:
        archived_text = site_row["archived_at"]
    except (TypeError, KeyError, IndexError) as error:
        raise ValidationError("site row required") from error
    if archived_text is not None:
        raise ConflictError(ARCHIVED_SITE_MESSAGE)
    return None
