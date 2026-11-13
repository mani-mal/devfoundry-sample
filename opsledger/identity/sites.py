"""Site membership domain module for OpsLedger (T014, M2/T014, spec §7.2/§7.3).

Site memberships
================

Users are granted access to specific sites within their organization. The
``site_memberships`` table shape is
``(organization_id, site_id, user_id, granted_at, revoked_at)`` with PK
``(organization_id, site_id, user_id)`` -- its storage migration lands in
the follow-up task; this module documents the shape and reads over row data
matching it.

Immediate effect
================

Deactivating a membership deletes the membership row (the existing
``memberships`` table has no active marker, so the DELETE is the
deactivation); revoking a site grant stamps the row's ``revoked_at``. Both
take effect IMMEDIATELY: an existing session loses access on
deactivation/site revocation because every check reads current state --
access checks join memberships and read ``revoked_at IS NULL`` on the
current row -- with no caching anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass

from opsledger.core.db import transaction
from opsledger.core.errors import PermissionDeniedError, ValidationError

__all__ = [
    "SiteGrant",
    "site_access_active",
    "require_site_access",
    "has_site_access",
    "deactivate_membership",
    "revoke_site_grant",
    "active_site_ids",
]


_MISSING = object()

_SITE_GRANT_FIELDS = (
    "organization_id",
    "site_id",
    "user_id",
    "granted_at",
    "revoked_at",
)


@dataclass(frozen=True)
class SiteGrant:
    """One site grant: a user granted access to one site, at one instant."""

    organization_id: str
    site_id: str
    user_id: str
    granted_at: str
    revoked_at: str | None = None


def _read_field(value: object, name: str) -> object:
    """Read ``name`` off a dict, mapping, or object defensively."""
    if isinstance(value, dict):
        return value.get(name, _MISSING)
    try:
        return value[name]
    except (TypeError, KeyError, IndexError):
        return getattr(value, name, _MISSING)


def _require_context_field(context: object, name: str) -> str:
    field = _read_field(context, name)
    if not isinstance(field, str) or not field:
        raise ValidationError("valid site membership context required")
    return field


def site_access_active(grant: object) -> bool:
    """Pure predicate: True only when the grant's ``revoked_at`` is None.

    Reads ``revoked_at`` defensively (``getattr`` or ``["revoked_at"]``):
    a present non-None text counts as revoked. Raises ValidationError for
    a non-grant-like object without the fields.
    """
    for name in _SITE_GRANT_FIELDS:
        if _read_field(grant, name) is _MISSING:
            raise ValidationError("valid site grant required")
    return _read_field(grant, "revoked_at") is None


def _matches(grant: object, organization_id: str, site_id: str) -> bool:
    if _read_field(grant, "revoked_at") is not None:
        return False
    return _read_field(grant, "organization_id") == organization_id and _read_field(
        grant, "site_id"
    ) == site_id


def require_site_access(context: object, grants: list) -> None:
    """Canonical immediate-revocation check for one target site.

    Raises PermissionDeniedError with message ``"no access to this site"``
    unless some active grant in ``grants`` matches BOTH
    ``context.organization_id`` AND the target site (``context.site_id``).
    Passes silently when one does. Grants are read defensively; each may be
    any object with the fields. ValidationError on a malformed context.
    """
    organization_id = _require_context_field(context, "organization_id")
    site_id = _require_context_field(context, "site_id")
    for grant in grants:
        if _read_field(grant, "revoked_at") is not None:
            continue
        if _read_field(grant, "organization_id") == organization_id and _read_field(
            grant, "site_id"
        ) == site_id:
            return
    raise PermissionDeniedError("no access to this site")


def has_site_access(context: object, grants: list) -> bool:
    """Pure predicate version of the same check; never raises for ordinary checks."""
    try:
        require_site_access(context, grants)
    except PermissionDeniedError:
        return False
    return True


def deactivate_membership(
    conn: object,
    *,
    organization_id: str,
    user_id: str,
    clock: object,
) -> None:
    """Delete one membership row; the DELETE is the deactivation.

    Runs in one transaction on ``conn``. Deleting the row deactivates the
    membership immediately: access checks join memberships, so every
    session loses access as soon as the row is gone (checks read current
    state). No-op when the row does not exist; never raises for a missing
    row.
    """
    with transaction(conn) as tx:
        tx.execute(
            "DELETE FROM memberships WHERE organization_id = ? AND user_id = ?",
            (organization_id, user_id),
        )


def revoke_site_grant(conn: object, *, grant: SiteGrant, clock: object) -> None:
    """Stamp one site grant's ``revoked_at`` with the clock's RFC3339 Z text.

    Runs in one transaction on ``conn``: parameterized
    ``UPDATE site_memberships SET revoked_at = ? WHERE organization_id = ?
    AND site_id = ? AND user_id = ? AND revoked_at IS NULL``. No-op when no
    active grant matches (an already-revoked grant is left unchanged).
    """
    revoked_text = clock.timestamp()
    with transaction(conn) as tx:
        tx.execute(
            "UPDATE site_memberships SET revoked_at = ?"
            " WHERE organization_id = ? AND site_id = ? AND user_id = ?"
            " AND revoked_at IS NULL",
            (revoked_text, grant.organization_id, grant.site_id, grant.user_id),
        )


def active_site_ids(conn: object, context: object) -> list[str]:
    """Return the unrevoked site ids granted to the context's user.

    Parameterized ``SELECT site_id FROM site_memberships WHERE
    organization_id = ? AND user_id = ? AND revoked_at IS NULL``. Empty
    list when none.
    """
    organization_id = _require_context_field(context, "organization_id")
    user_id = _require_context_field(context, "user_id")
    cursor = conn.execute(
        "SELECT site_id FROM site_memberships"
        " WHERE organization_id = ? AND user_id = ? AND revoked_at IS NULL",
        (organization_id, user_id),
    )
    rows = cursor.fetchall()
    return [row["site_id"] for row in rows]
