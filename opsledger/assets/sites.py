"""Sites domain module for OpsLedger: create/list/update (T017, M3).

Scoping rule (spec M3/T017): site codes are scoped per organization. The
UNIQUE constraint is ``(organization_id, code)``, so the same code in
another organization is allowed and a duplicate in the same organization is
refused with the one canonical message :data:`DUPLICATE_SITE_CODE_MESSAGE`.
Every lookup is guarded by :func:`opsledger.core.context.require_owned`:
a missing site and a site owned by another organization surface the same
:data:`SITE_NOT_FOUND_MESSAGE` NotFoundError — no existence leak.
"""

from __future__ import annotations

import sqlite3
import uuid

from opsledger.core.clock import Clock, RealClock, format_rfc3339, require_aware_utc
from opsledger.core.db import transaction
from opsledger.core.context import (
    OrganizationContext,
    require_context,
    require_owned,
    scoped_first,
    scoped_all,
)
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError

__all__ = [
    "DUPLICATE_SITE_CODE_MESSAGE",
    "SITE_NOT_FOUND_MESSAGE",
    "create_site",
    "get_site",
    "list_sites",
    "update_site",
]

DUPLICATE_SITE_CODE_MESSAGE = "site code already exists in this organization"

SITE_NOT_FOUND_MESSAGE = "site not found"

_SELECT_SITE_BY_ID_SQL = (
    "SELECT id, organization_id, code, name, timezone, created_at, archived_at"
    " FROM sites WHERE id = ?"
)

_INSERT_SITE_SQL = (
    "INSERT INTO sites (id, organization_id, code, name, timezone, created_at)"
    " VALUES (?, ?, ?, ?, ?, ?)"
)

_LIST_SITE_BASE_SQL = (
    "SELECT id, organization_id, code, name, timezone, created_at, archived_at"
    " FROM sites WHERE organization_id = ?"
)

_UPDATE_SITE_NAME_SQL = "UPDATE sites SET name = ? WHERE id = ?"

_UPDATE_SITE_TIMEZONE_SQL = "UPDATE sites SET timezone = ? WHERE id = ?"


def _validate_code(code: str) -> str:
    """Normalize and validate a site code; return the stripped value."""
    if not isinstance(code, str) or not code.strip():
        raise ValidationError(
            "site code must contain only lowercase letters, digits and hyphens"
        )
    stripped = code.strip()
    if not all(char in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in stripped):
        raise ValidationError(
            "site code must contain only lowercase letters, digits and hyphens"
        )
    return stripped


def _require_name(name: object) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValidationError("site name required")
    return name


def _require_timezone_name(timezone_name: object) -> str:
    if not isinstance(timezone_name, str) or not timezone_name.strip():
        raise ValidationError("site timezone required")
    return timezone_name.strip()


def create_site(
    conn: sqlite3.Connection,
    context: object,
    *,
    code: str,
    name: str,
    timezone_name: str = "UTC",
    clock: Clock,
) -> sqlite3.Row:
    """Insert one site for the authenticated organization.

    require_context(context); the code is normalized/validated by
    _validate_code; name and timezone_name must be non-empty strings. The
    row is inserted inside one transaction(conn) with created_at
    serialized canonically via format_rfc3339(clock.now()). A same-org
    duplicate violates the (organization_id, code) UNIQUE constraint and
    surfaces ConflictError with DUPLICATE_SITE_CODE_MESSAGE (nothing
    stored); another organization may reuse the code (scoping rule).
    """
    require_context(context)
    validated_code = _validate_code(code)
    validated_name = _require_name(name)
    validated_timezone = _require_timezone_name(timezone_name)
    site_id = "site-" + uuid.uuid4().hex
    created_text = format_rfc3339(clock.now())
    try:
        with transaction(conn) as tx:
            tx.execute(
                _INSERT_SITE_SQL,
                (
                    site_id,
                    context.organization_id,
                    validated_code,
                    validated_name,
                    validated_timezone,
                    created_text,
                ),
            )
    except sqlite3.IntegrityError as error:
        raise ConflictError(DUPLICATE_SITE_CODE_MESSAGE) from error
    return conn.execute(_SELECT_SITE_BY_ID_SQL, (site_id,)).fetchone()


def get_site(
    conn: sqlite3.Connection,
    context: object,
    *,
    site_id: str,
) -> sqlite3.Row:
    """SELECT the site row by id and guard it with require_owned.

    A missing site and a cross-organization site raise the identical
    NotFoundError (label "site") — callers can never learn which case
    occurred (require_owned flow, spec).
    """
    row = conn.execute(_SELECT_SITE_BY_ID_SQL, (site_id,)).fetchone()
    require_owned(require_context(context), row, label="site")
    return row


def list_sites(
    conn: sqlite3.Connection,
    context: object,
    *,
    include_archived: bool = False,
) -> list[sqlite3.Row]:
    """List the organization's sites, ordered by created_at then id.

    scoped_all over SELECT ... FROM sites WHERE organization_id = ?
    (+ AND archived_at IS NULL when not include_archived) ORDER BY
    created_at, id — only in-scope rows are returned, in order.
    """
    context = require_context(context)
    sql = _LIST_SITE_BASE_SQL
    if not include_archived:
        sql += " AND archived_at IS NULL"
    sql += " ORDER BY created_at, id"
    return scoped_all(conn, context, sql, (context.organization_id,))


def update_site(
    conn: sqlite3.Connection,
    context: object,
    *,
    site_id: str,
    name: str | None = None,
    timezone_name: str | None = None,
    clock: Clock,
) -> sqlite3.Row:
    """Update the provided fields of one owned site; re-select and return.

    require_context; SELECT the row by id and require_owned (label "site");
    UPDATE only the provided fields (name and/or timezone) in one
    transaction(conn); re-SELECT and return the updated row, re-guarded.
    Code is immutable: it is never updated after creation — there is no
    code update path in this module.
    """
    require_context(context)
    row = conn.execute(_SELECT_SITE_BY_ID_SQL, (site_id,)).fetchone()
    require_owned(context, row, label="site")
    if name is not None:
        _require_name(name)
    if timezone_name is not None:
        _require_timezone_name(timezone_name)
    with transaction(conn) as tx:
        if name is not None:
            tx.execute(_UPDATE_SITE_NAME_SQL, (name, site_id))
        if timezone_name is not None:
            tx.execute(_UPDATE_SITE_TIMEZONE_SQL, (timezone_name.strip(), site_id))
    updated = conn.execute(_SELECT_SITE_BY_ID_SQL, (site_id,)).fetchone()
    require_owned(context, updated, label="site")
    return updated
