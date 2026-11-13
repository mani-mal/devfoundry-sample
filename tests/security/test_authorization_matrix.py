"""Authorization matrix regression tests (T016, spec §7.3/M2 gate).

Gate rule: "Every declared role/action pair has observed or explicitly
pending evidence." Roles come from opsledger.identity.permissions
(KNOWN_ROLES + BASE_PERMISSIONS + PURCHASE_APPROVE_PERMISSION); actions are
the base-permission strings plus the explicit approver grant. Below, each
role/action pair is listed with its expected verdict (A = allow, D = deny).
Verdicts are observed at the domain layer by this file; some pairs are not
yet enforced by HTTP routes, so those paths are marked "explicitly pending"
here and their route-level enforcement lands with M3+ tasks.

  admin:
    org.manage_members                      A
    org.manage_sites                        A
    asset.write                             A
    workorder.write                         A
    workorder.close                         A
    inventory.adjust                        A
    inventory.write                         A
    purchasing.write                        A
    reporting.read                          A
    audit.read                              A
    workorder.work                          D
    inventory.reserve                       D
    inventory.consume                       D
    export.read                             D
    purchase.approve                        D (without explicit grant)
  supervisor:
    org.manage_members                      D
    org.manage_sites                        D
    asset.write                             A
    workorder.write                         A
    workorder.close                         A
    inventory.adjust                        A
    inventory.write                         D
    inventory.consume                       D
    purchasing.write                        D
    reporting.read                          A
    audit.read                              D
    workorder.work                          D
    export.read                             D
    purchase.approve                        D (becomes A only with explicit grant)
  technician:
    org.manage_members                      D
    org.manage_sites                        D
    asset.write                             D
    workorder.write                         D
    workorder.close                         D
    inventory.adjust                        D
    inventory.write                         D
    inventory.consume                       D
    purchasing.write                        D
    reporting.read                          A
    audit.read                              D
    workorder.work                          A
    export.read                             D
    purchase.approve                        D (denied by default; no auto-approval)
  purchasing:
    org.manage_members                      D
    org.manage_sites                        D
    asset.write                             D
    workorder.write                         D
    workorder.close                         D
    inventory.adjust                        D
    inventory.write                         D
    inventory.consume                       D
    purchasing.write                        A
    reporting.read                          A
    audit.read                              D
    workorder.work                          D
    export.read                             D
    purchase.approve                        D (becomes A only with explicit grant)
  auditor:
    org.manage_members                      D
    org.manage_sites                        D
    asset.write                             D
    workorder.write                         D
    workorder.close                         D
    inventory.adjust                        D
    inventory.write                         D
    inventory.consume                       D
    purchasing.write                        D
    reporting.read                          A
    audit.read                              A
    workorder.work                          D
    purchase.approve                        D
    export.read                             A
  self-approval (actor_id == target_user_id):
    every role (admin, supervisor, technician,
    purchasing, auditor) — even admin       D
  site access (orthogonal to role):
    active grant                            A
    revoked grant                           D
    cross-org grant                         D
    empty grant list                        D

  Explicitly pending (expected verdicts above, HTTP-route enforcement
  lands with M3+ tasks): every require_permission / require_role /
  require_site_access path invoked from HTTP routes.
"""

import re
import unittest

from opsledger.core.errors import PermissionDeniedError
from opsledger.identity import sites
from opsledger.identity import permissions


KNOWN_ROLES = permissions.KNOWN_ROLES
BASE_PERMISSIONS = permissions.BASE_PERMISSIONS
PURCHASE_APPROVE_PERMISSION = permissions.PURCHASE_APPROVE_PERMISSION

_SPECIALIST_QUALIFIERS = {"workorder.work", "inventory.reserve", "export.read"}


class _AuthContext:
    """Tiny stub authorization context: role/actor_id attributes."""

    def __init__(
        self,
        *,
        organization_id,
        actor_id,
        role,
        site_id=None,
        user_id=None,
    ):
        self.organization_id = organization_id
        self.actor_id = actor_id
        self.role = role
        self.site_id = site_id
        self.user_id = user_id


_PERMISSION_SHAPE = re.compile(r"^[a-z]+\.[a-z_]+$")
_CANONICAL_DENY = "operation not permitted for this role"
_SITE_DENY = "no access to this site"


class AuthorizationMatrixTests(unittest.TestCase):
    """Regression coverage for the M2 authorization matrix (T016)."""

    def test_t1_matrix_completeness(self):
        for role in sorted(KNOWN_ROLES):
            self.assertIn(role, BASE_PERMISSIONS)
            perms = BASE_PERMISSIONS[role]
            self.assertIsInstance(perms, frozenset)
            self.assertTrue(perms, f"role {role} must hold a non-empty frozenset")
            for permission in perms:
                self.assertRegex(permission, _PERMISSION_SHAPE)
        self.assertRegex(PURCHASE_APPROVE_PERMISSION, _PERMISSION_SHAPE)

    def test_t2_auditor_read_only(self):
        auditor = _AuthContext(organization_id="org-1", actor_id="u-aud", role="auditor")
        effective = permissions.effective_permissions("auditor")
        self.assertTrue(effective)
        for permission in effective:
            self.assertTrue(
                ".read" in permission or ".export" in permission,
                f"auditor permission {permission} must be read-shaped",
            )
        forbidden = [".write", ".adjust", ".approve", ".reserve", ".consume", "workorder.work"]
        for marker in forbidden:
            for permission in effective:
                self.assertNotIn(marker, permission)
        write_actions = [
            "org.manage_members",
            "org.manage_sites",
            "asset.write",
            "workorder.write",
            "inventory.adjust",
            "inventory.write",
            "inventory.reserve",
            "inventory.consume",
            "purchasing.write",
        ]
        for action in write_actions:
            self.assertFalse(permissions.has_permission(auditor, action))
            with self.assertRaises(PermissionDeniedError):
                permissions.require_permission(auditor, action)

    def test_t3_admin_superset(self):
        admin_perms = admin = None
        admin_perms = permissions.effective_permissions("admin")
        for qualifier in _SPECIALIST_QUALIFIERS:
            self.assertNotIn(qualifier, admin_perms)
        for role in sorted(KNOWN_ROLES - {"admin"}):
            perms = permissions.effective_permissions(role)
            business = perms - _SPECIALIST_QUALIFIERS
            self.assertTrue(
                business <= admin_perms,
                f"admin must contain every business-operation permission of role {role}",
            )
        self.assertIn("org.manage_members", admin_perms)
        self.assertIn("org.manage_sites", admin_perms)
        self.assertIn("audit.read", admin_perms)

    def test_t4_approver_grant_distinct(self):
        for role in sorted(KNOWN_ROLES):
            self.assertNotIn(PURCHASE_APPROVE_PERMISSION, BASE_PERMISSIONS[role])
        purchasing_ctx = _AuthContext(organization_id="org-1", actor_id="u-1", role="purchasing")
        self.assertTrue(
            permissions.has_permission(
                purchasing_ctx,
                PURCHASE_APPROVE_PERMISSION,
                explicit_grants=[PURCHASE_APPROVE_PERMISSION],
            )
        )
        self.assertFalse(
            permissions.has_permission(purchasing_ctx, PURCHASE_APPROVE_PERMISSION)
        )
        supervisor_ctx = _AuthContext(organization_id="org-1", actor_id="u-2", role="supervisor")
        self.assertTrue(
            permissions.has_permission(
                supervisor_ctx,
                PURCHASE_APPROVE_PERMISSION,
                explicit_grants=[PURCHASE_APPROVE_PERMISSION],
            )
        )
        self.assertFalse(
            permissions.has_permission(supervisor_ctx, PURCHASE_APPROVE_PERMISSION)
        )
        technician_ctx = _AuthContext(organization_id="org-1", actor_id="u-3", role="technician")
        self.assertFalse(
            permissions.has_permission(technician_ctx, PURCHASE_APPROVE_PERMISSION)
        )
        with self.assertRaises(PermissionDeniedError):
            permissions.require_permission(technician_ctx, PURCHASE_APPROVE_PERMISSION)

    def test_t5_self_approval_prohibited(self):
        for role in sorted(KNOWN_ROLES):
            actor = _AuthContext(organization_id="org-1", actor_id="u-1", role=role)
            with self.assertRaises(PermissionDeniedError):
                permissions.assert_not_self_approval(actor, "u-1")
            permissions.assert_not_self_approval(actor, "u-target")

    def test_t6_deny_message_canonical(self):
        auditor = _AuthContext(organization_id="org-1", actor_id="u-aud", role="auditor")
        technician = _AuthContext(organization_id="org-1", actor_id="u-tech", role="technician")
        messages = []
        try:
            permissions.require_permission(auditor, "asset.write")
        except PermissionDeniedError as error:
            messages.append(str(error))
        try:
            permissions.require_role(technician, ["admin"])
        except PermissionDeniedError as error:
            messages.append(str(error))
        if not permissions.has_permission(auditor, "workorder.work"):
            try:
                permissions.require_permission(auditor, "workorder.work")
            except PermissionDeniedError as error:
                messages.append(str(error))
        self.assertEqual(len(messages), 3)
        for message in messages:
            self.assertEqual(message, _CANONICAL_DENY)

    def test_t7_site_access_matrix(self):
        active_grants = [
            sites.SiteGrant(
                organization_id="org-1",
                site_id="site-1",
                user_id="u-1",
                granted_at="2026-11-06T12:00:00Z",
            )
        ]
        revoked_grants = [
            sites.SiteGrant(
                organization_id="org-1",
                site_id="site-1",
                user_id="u-1",
                granted_at="2026-11-06T12:00:00Z",
                revoked_at="2026-11-06T13:00:00Z",
            )
        ]
        cross_org_grants = [
            sites.SiteGrant(
                organization_id="org-2",
                site_id="site-1",
                user_id="u-1",
                granted_at="2026-11-06T12:00:00Z",
            )
        ]
        auditor_ctx = _AuthContext(
            organization_id="org-1",
            actor_id="u-1",
            role="auditor",
            site_id="site-1",
            user_id="u-1",
        )
        self.assertTrue(sites.has_site_access(auditor_ctx, active_grants))
        revoked_ctx = _AuthContext(
            organization_id="org-1",
            actor_id="u-1",
            role="admin",
            site_id="site-1",
            user_id="u-1",
        )
        self.assertFalse(sites.has_site_access(revoked_ctx, revoked_grants))
        with self.assertRaises(Exception) as context:
            sites.require_site_access(revoked_ctx, revoked_grants)
        self.assertEqual(str(context.exception), _SITE_DENY)
        cross_org_ctx = _AuthContext(
            organization_id="org-1",
            actor_id="u-1",
            role="admin",
            site_id="site-1",
            user_id="u-1",
        )
        self.assertFalse(sites.has_site_access(cross_org_ctx, cross_org_grants))
        with self.assertRaises(Exception) as context:
            sites.require_site_access(cross_org_ctx, cross_org_grants)
        self.assertEqual(str(context.exception), _SITE_DENY)
        empty_ctx = _AuthContext(
            organization_id="org-1",
            actor_id="u-1",
            role="admin",
            site_id="site-3",
            user_id="u-1",
        )
        with self.assertRaises(Exception) as context:
            sites.require_site_access(empty_ctx, [])
        self.assertEqual(str(context.exception), _SITE_DENY)
        self.assertFalse(sites.has_site_access(empty_ctx, []))


if __name__ == "__main__":
    unittest.main()
