"""Organization identity context for OpsLedger (T012).

IDs are not authorization: every lookup and join requires the authenticated
organization context. An unknown resource and a resource owned by another
organization are indistinguishable to callers -- one canonical error message,
no existence leak.
"""

from __future__ import annotations

from dataclasses import dataclass

from opsledger.core.errors import NotFoundError, ValidationError

__all__ = [
    "OrganizationContext",
    "require_context",
    "require_owned",
    "scoped_first",
    "scoped_all",
]


@dataclass(frozen=True)
class OrganizationContext:
    """Authenticated organization identity carried by every lookup."""

    organization_id: str
    actor_id: str | None = None


def require_context(value: object) -> OrganizationContext:
    """Return the context unchanged, or raise ValidationError."""
    if not isinstance(value, OrganizationContext):
        raise ValidationError("organization context required")
    if not isinstance(value.organization_id, str) or not value.organization_id:
        raise ValidationError("organization context required")
    return value


def _read_row_organization_id(row: object) -> object:
    """Read the row's organization_id defensively; missing means not-owned."""
    if isinstance(row, dict):
        return row.get("organization_id")
    try:
        return row["organization_id"]
    except (TypeError, KeyError, IndexError):
        return getattr(row, "organization_id", None)


def require_owned(
    context: object,
    row: object,
    *,
    label: str = "resource",
) -> object:
    """Canonical no-leak guard: return the row when owned, else NotFoundError.

    A missing record (None) and a record owned by another organization raise
    the same error shape; callers can never learn which case occurred.
    """
    require_context(context)
    if row is None:
        raise NotFoundError(f"{label} not found")
    if _read_row_organization_id(row) != context.organization_id:
        raise NotFoundError(f"{label} not found")
    return row


def scoped_all(
    conn: object,
    context: object,
    sql: str,
    params: tuple = (),
) -> list:
    """Execute the caller's SELECT and keep only in-scope rows, in order."""
    require_context(context)
    cursor = conn.execute(sql, params)
    rows = cursor.fetchall()
    return [row for row in rows if _read_row_organization_id(row) == context.organization_id]


def scoped_first(
    conn: object,
    context: object,
    sql: str,
    params: tuple = (),
):
    """Execute the caller's SELECT; return the first in-scope row or None."""
    require_context(context)
    cursor = conn.execute(sql, params)
    row = cursor.fetchone()
    if row is None:
        return None
    if _read_row_organization_id(row) != context.organization_id:
        return None
    return row
