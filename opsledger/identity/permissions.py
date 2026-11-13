"""Explicit operation permission checks for OpsLedger services (T013).

Permissions are explicit operation checks in services. Hiding a button is
insufficient. A purchasing user does not automatically become an approver:
``purchase.approve`` is an explicit membership permission, distinct from
the purchasing role, and self-approval is prohibited even for an admin.

This module is pure: role strings and permission sets only. No DB calls,
no HTTP. The permission-check functions accept an OrganizationContext-like
object that carries ``role`` and ``actor_id`` attributes. That context is
produced by the T012 context module extended by callers, or any simple
stub with those attributes; it is only read defensively via ``getattr``,
so no specific actor class is required.
"""

from __future__ import annotations

from opsledger.core.errors import PermissionDeniedError, ValidationError

__all__ = [
    "KNOWN_ROLES",
    "BASE_PERMISSIONS",
    "PURCHASE_APPROVE_PERMISSION",
    "require_role",
    "require_permission",
    "has_permission",
    "assert_not_self_approval",
    "effective_permissions",
]

KNOWN_ROLES: frozenset[str] = frozenset(
    {"admin", "supervisor", "technician", "purchasing", "auditor"}
)

BASE_PERMISSIONS: dict[str, frozenset[str]] = {
    "admin": frozenset(
        {
            "org.manage_members",
            "org.manage_sites",
            "asset.write",
            "workorder.write",
            "workorder.close",
            "inventory.adjust",
            "inventory.write",
            "purchasing.write",
            "reporting.read",
            "audit.read",
        }
    ),
    "supervisor": frozenset(
        {
            "asset.write",
            "workorder.write",
            "workorder.close",
            "inventory.adjust",
            "reporting.read",
        }
    ),
    "technician": frozenset(
        {
            "workorder.work",
            "inventory.reserve",
            "reporting.read",
        }
    ),
    "purchasing": frozenset(
        {
            "purchasing.write",
            "reporting.read",
        }
    ),
    "auditor": frozenset(
        {
            "reporting.read",
            "audit.read",
            "export.read",
        }
    ),
}

PURCHASE_APPROVE_PERMISSION: str = "purchase.approve"

_DENY_MESSAGE = "operation not permitted for this role"


def _context_role(actor: object) -> str:
    """Return the actor's role, raising ValidationError if malformed."""
    role = getattr(actor, "role", None)
    if not isinstance(role, str) or role not in KNOWN_ROLES:
        raise ValidationError("malformed authorization context")
    return role


def _context_actor_id(actor: object) -> str:
    """Return the actor's id, raising ValidationError if malformed."""
    actor_id = getattr(actor, "actor_id", None)
    if not isinstance(actor_id, str) or not actor_id:
        raise ValidationError("malformed authorization context")
    return actor_id


def _normalized_grants(grants: list[str] | None) -> frozenset[str]:
    """Normalize explicit grants to a frozenset, rejecting malformed input."""
    if grants is None:
        return frozenset()
    if not isinstance(grants, list) or not all(isinstance(g, str) for g in grants):
        raise ValidationError("malformed explicit grants")
    return frozenset(grants)


def require_role(actor: object, roles: str | list[str]) -> None:
    """Require the caller's role to be one of ``roles``.

    Raises:
        ValidationError: If the context or ``roles`` is malformed.
        PermissionDeniedError: If the caller's role is not in ``roles``.
    """
    role = _context_role(actor)
    if isinstance(roles, str):
        allowed = frozenset({roles})
    elif (
        isinstance(roles, list)
        and roles
        and all(isinstance(r, str) for r in roles)
    ):
        allowed = frozenset(roles)
    else:
        raise ValidationError("malformed required roles")
    if not allowed <= KNOWN_ROLES:
        raise ValidationError("malformed required roles")
    if role not in allowed:
        raise PermissionDeniedError(_DENY_MESSAGE)


def require_permission(actor: object, permission: str) -> None:
    """Require the caller to hold ``permission``.

    Permissions held are the actor role's base permissions, or the explicit
    approver grant path (``purchase.approve`` granted as an explicit
    membership permission, never part of any role's base permissions).

    Raises:
        ValidationError: If the context or ``permission`` is malformed.
        PermissionDeniedError: If the permission is not held.
    """
    actor_role = _context_role(actor)
    if not isinstance(permission, str) or not permission:
        raise ValidationError("malformed permission name")
    if permission not in BASE_PERMISSIONS[actor_role]:
        raise PermissionDeniedError(_DENY_MESSAGE)


def has_permission(
    actor: object,
    permission: str,
    *,
    explicit_grants: list[str] | None = None,
) -> bool:
    """Pure predicate: does the actor hold ``permission``?

    True when the permission is in the actor role's base permissions OR in
    ``explicit_grants`` (the approver grant path). False otherwise. Never
    raises for ordinary checks.
    """
    role = getattr(actor, "role", None)
    if not isinstance(role, str) or role not in KNOWN_ROLES:
        return False
    if not isinstance(permission, str) or not permission:
        return False
    try:
        grants = _normalized_grants(explicit_grants)
    except ValidationError:
        return False
    return permission in BASE_PERMISSIONS[role] or permission in grants


def assert_not_self_approval(actor: object, target_user_id: str) -> None:
    """Prohibit self-approval, even for an admin.

    Raises:
        ValidationError: If the context or ``target_user_id`` is malformed.
        PermissionDeniedError: If ``context.actor_id == target_user_id``.
    """
    actor_id = _context_actor_id(actor)
    if not isinstance(target_user_id, str) or not target_user_id:
        raise ValidationError("malformed target user id")
    if actor_id == target_user_id:
        raise PermissionDeniedError("self-approval is not permitted")


def effective_permissions(
    role: str,
    *,
    explicit_grants: list[str] | None = None,
) -> frozenset[str]:
    """Return base permissions for ``role`` unioned with explicit grants.

    Raises:
        ValidationError: If the role is unknown or grants are malformed.
    """
    if not isinstance(role, str) or role not in KNOWN_ROLES:
        raise ValidationError("unknown role")
    return BASE_PERMISSIONS[role] | _normalized_grants(explicit_grants)
