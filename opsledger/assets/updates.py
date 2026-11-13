"""Optimistic-concurrency asset updates for OpsLedger (T020, M3, §8.2).

The ``assets.version`` column exists from migration 0008 (CHECK version > 0)
and is bumped by exactly one on every successful update. SQLite has no
SELECT FOR UPDATE; the conditional UPDATE
``UPDATE assets SET ... WHERE id = ? AND version = ?`` is itself the
optimistic-concurrency check — the caller's ``expected_version`` either
matches the stored version (rowcount 1, change applied) or does not
(rowcount 0, a second writer moved the row). On contention nothing from this
writer is stored — the first writer's change is retained — and a
:class:`opsledger.core.errors.ConflictError` carrying
:data:`STALE_VERSION_MESSAGE` is raised as the bounded retryable error.
Each optional column is assigned ``col = COALESCE(?, col)`` so an
unprovided field (bound None) keeps its stored value on a partial update.

Scoping rule: every lookup is guarded by
:func:`opsledger.core.context.require_owned`; a missing asset and an asset
owned by another organization surface the identical NotFoundError.
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
    "STALE_VERSION_MESSAGE",
    "update_asset",
]

STALE_VERSION_MESSAGE = "asset was modified by someone else; reload and retry"

CRITICALITIES = frozenset({"low", "medium", "high"})

_SELECT_ASSET_BY_ID_SQL = (
    "SELECT id, organization_id, site_id, tag, name, criticality,"
    " purchase_cost_cents, version, created_at, updated_at, archived_at"
    " FROM assets WHERE id = ?"
)

_UPDATE_ASSET_SQL = (
    "UPDATE assets SET"
    " name = COALESCE(?, name),"
    " criticality = COALESCE(?, criticality),"
    " purchase_cost_cents = COALESCE(?, purchase_cost_cents),"
    " version = version + 1,"
    " updated_at = ?"
    " WHERE id = ? AND version = ?"
)


def _validate_expected_version(expected_version: object) -> int:
    """Require an int (not bool) > 0 for the caller's expected version."""
    if isinstance(expected_version, bool) or not isinstance(expected_version, int):
        raise ValidationError("expected version must be a positive integer")
    if expected_version <= 0:
        raise ValidationError("expected version must be a positive integer")
    return expected_version


def _has_fields_to_update(
    name: object,
    criticality: object,
    purchase_cost_cents: object,
) -> bool:
    """Return True when at least one field to update was provided."""
    return (
        name is not None or criticality is not None or purchase_cost_cents is not None
    )


def _validate_criticality(criticality: str) -> str:
    if criticality not in CRITICALITIES:
        raise ValidationError("criticality must be one of: low, medium, high")
    return criticality


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


def update_asset(
    conn: sqlite3.Connection,
    context: object,
    *,
    asset_id: str,
    expected_version: int,
    name: str | None = None,
    criticality: str | None = None,
    purchase_cost_cents: int | None = None,
    clock: Clock,
) -> sqlite3.Row:
    """Update one asset with optimistic-concurrency version checking.

    require_context(context); expected_version must be an int (not bool)
    > 0; at least one of name/criticality/purchase_cost_cents must be
    provided; criticality is validated by _validate_criticality;
    purchase_cost_cents is validated by _validate_purchase_cost (money is
    integer cents). NO LEAK: the asset row is SELECTed and surfaced by
    require_owned(label "asset"), so a cross-organization asset raises the
    identical NotFoundError as a missing asset. The row is updated inside
    one transaction(conn) with an ATOMIC CONDITIONAL UPDATE — every value a
    bound parameter and each optional column assigned ``col = COALESCE(?,
    col)`` so unprovided fields keep their stored values. When the UPDATE
    reports rowcount 0 (the version moved), the row is re-SELECTed: if it
    exists, ConflictError carrying STALE_VERSION_MESSAGE is raised — the
    FIRST writer's change is retained and this update simply fails. When
    rowcount 1, the updated row is re-SELECTed and returned (version
    incremented by exactly 1).
    """
    require_context(context)
    validated_expected_version = _validate_expected_version(expected_version)
    if not _has_fields_to_update(name, criticality, purchase_cost_cents):
        raise ValidationError("no fields to update")
    validated_criticality = (
        _validate_criticality(criticality) if criticality is not None else None
    )
    validated_cost = (
        _validate_purchase_cost(purchase_cost_cents)
        if purchase_cost_cents is not None
        else None
    )
    asset_row = conn.execute(_SELECT_ASSET_BY_ID_SQL, (asset_id,)).fetchone()
    require_owned(context, asset_row, label="asset")
    timestamp_text = format_rfc3339(clock.now())
    try:
        with transaction(conn) as tx:
            tx_cursor = tx.execute(
                _UPDATE_ASSET_SQL,
                (
                    name,
                    validated_criticality,
                    validated_cost,
                    timestamp_text,
                    asset_id,
                    validated_expected_version,
                ),
            )
    except sqlite3.IntegrityError as error:
        raise ConflictError(STALE_VERSION_MESSAGE) from error
    if tx_cursor.rowcount == 0:
        raise ConflictError(STALE_VERSION_MESSAGE) from None
    return conn.execute(_SELECT_ASSET_BY_ID_SQL, (asset_id,)).fetchone()
