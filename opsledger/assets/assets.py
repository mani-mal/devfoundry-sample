"""Assets domain module for OpsLedger: site-scoped create/get (T018, M3).

Scoping rule (spec M3/T018): asset tags are scoped per organization. The
UNIQUE constraint is ``(organization_id, tag)``, so the same tag in another
organization is allowed and a duplicate in the same organization is refused
with the one canonical message :data:`DUPLICATE_ASSET_TAG_MESSAGE`. An asset
is created on a site in the caller's organization only: the site row is
selected with :func:`opsledger.core.context.scoped_first` and guarded by
:func:`opsledger.core.context.require_owned`, so a cross-organization site is
indistinguishable from a missing site — no existence leak. Every lookup is
guarded by :func:`opsledger.core.context.require_owned`: a missing asset and
an asset owned by another organization surface the same NotFoundError.
"""

from __future__ import annotations

import sqlite3
import uuid

from opsledger.core.clock import Clock, format_rfc3339
from opsledger.core.db import transaction
from opsledger.core.context import (
    OrganizationContext,
    require_context,
    require_owned,
    scoped_first,
)
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError

__all__ = [
    "DUPLICATE_ASSET_TAG_MESSAGE",
    "CRITICALITIES",
    "create_asset",
    "get_asset",
]

DUPLICATE_ASSET_TAG_MESSAGE = "asset tag already exists in this organization"

CRITICALITIES = frozenset({"low", "medium", "high"})

_SELECT_ASSET_BY_ID_SQL = (
    "SELECT id, organization_id, site_id, tag, name, criticality,"
    " purchase_cost_cents, version, created_at, updated_at, archived_at"
    " FROM assets WHERE id = ?"
)

_INSERT_ASSET_SQL = (
    "INSERT INTO assets (id, organization_id, site_id, tag, name, criticality,"
    " purchase_cost_cents, version, created_at, updated_at, archived_at)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_SELECT_SITE_ROW_FOR_ASSET_SQL = (
    "SELECT id, organization_id, code, name, timezone, created_at, archived_at"
    " FROM sites WHERE id = ?"
)


def _validate_tag(tag: str) -> str:
    """Normalize and validate an asset tag; return the stripped value."""
    if not isinstance(tag, str) or not tag.strip():
        raise ValidationError(
            "asset tag must contain only lowercase letters, digits and hyphens"
        )
    stripped = tag.strip()
    if not all(char in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in stripped):
        raise ValidationError(
            "asset tag must contain only lowercase letters, digits and hyphens"
        )
    return stripped


def _validate_purchase_cost(purchase_cost_cents: object) -> int:
    if isinstance(purchase_cost_cents, bool) or not isinstance(purchase_cost_cents, int):
        raise ValidationError(
            "purchase cost must be a non-negative integer number of cents"
        )
    if purchase_cost_cents < 0:
        raise ValidationError(
            "purchase cost must be a non-negative integer number of cents"
        )
    return purchase_cost_cents


def _validate_criticality(criticality: str) -> str:
    if criticality not in CRITICALITIES:
        raise ValidationError("criticality must be one of: low, medium, high")
    return criticality


def _require_name(name: object) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValidationError("asset name required")
    return name


def create_asset(
    conn: sqlite3.Connection,
    context: object,
    *,
    site_id: str,
    tag: str,
    name: str,
    criticality: str,
    purchase_cost_cents: int,
    clock: Clock,
) -> sqlite3.Row:
    """Insert one asset on an in-scope site for the authenticated organization.

    require_context(context); the tag is normalized/validated by _validate_tag;
    name must be a non-empty string; criticality is validated by
    _validate_criticality; purchase_cost_cents is validated by
    _validate_purchase_cost (money is integer cents). SERVICE-LEVEL SITE
    SCOPING: the site row is SELECTed with scoped_first and surfaced by
    require_owned(label "site"), so a cross-organization site raises the
    identical "site not found" NotFoundError as a missing site. The row is
    inserted inside one transaction(conn) with both timestamps serialized
    canonically via format_rfc3339(clock.now()) and archived_at NULL. A
    same-org duplicate surfaces ConflictError with
    DUPLICATE_ASSET_TAG_MESSAGE (nothing stored); another organization may
    reuse the tag (scoping rule).
    """
    require_context(context)
    validated_tag = _validate_tag(tag)
    validated_name = _require_name(name)
    validated_criticality = _validate_criticality(criticality)
    validated_cost = _validate_purchase_cost(purchase_cost_cents)
    site_row = scoped_first(
        conn,
        context,
        _SELECT_SITE_ROW_FOR_ASSET_SQL,
        (site_id,),
    )
    require_owned(context, site_row, label="site")
    asset_id = "ast-" + uuid.uuid4().hex
    timestamp_text = format_rfc3339(clock.now())
    try:
        with transaction(conn) as tx:
            tx.execute(
                _INSERT_ASSET_SQL,
                (
                    asset_id,
                    context.organization_id,
                    site_id,
                    validated_tag,
                    validated_name,
                    validated_criticality,
                    validated_cost,
                    1,
                    timestamp_text,
                    timestamp_text,
                    None,
                ),
            )
    except sqlite3.IntegrityError as error:
        raise ConflictError(DUPLICATE_ASSET_TAG_MESSAGE) from error
    return conn.execute(_SELECT_ASSET_BY_ID_SQL, (asset_id,)).fetchone()


def get_asset(
    conn: sqlite3.Connection,
    context: object,
    *,
    asset_id: str,
) -> sqlite3.Row:
    """SELECT the asset row by id and guard it with require_owned.

    A missing asset and a cross-organization asset raise the identical
    NotFoundError (label "asset") — callers can never learn which case
    occurred (require_owned flow, spec).
    """
    row = conn.execute(_SELECT_ASSET_BY_ID_SQL, (asset_id,)).fetchone()
    require_owned(require_context(context), row, label="asset")
    return row
