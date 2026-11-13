"""Unit tests for explicit permission checks (T013): pure, stub contexts."""

from __future__ import annotations

import unittest

from opsledger.core.errors import PermissionDeniedError, ValidationError
from opsledger.identity import (
    BASE_PERMISSIONS,
    KNOWN_ROLES,
    PURCHASE_APPROVE_PERMISSION,
    assert_not_self_approval,
    effective_permissions,
    has_permission,
    require_permission,
    require_role,
)

_DENY_MESSAGE = "operation not permitted for this role"


class StubContext:
    """Tiny authorization context with role/actor_id attributes."""

    def __init__(self, role: str, actor_id: str) -> None:
        self.role = role
        self.actor_id = actor_id


def ctx(role: str) -> StubContext:
    return StubContext(role, f"user-{role}")


class TestPermissions(unittest.TestCase):
    def test_t1_auditor_has_no_write_permission(self):
        auditor = ctx("auditor")
        self.assertFalse(has_permission(auditor, "asset.write"))
        self.assertFalse(has_permission(auditor, "workorder.write"))
        self.assertFalse(has_permission(auditor, "inventory.adjust"))
        self.assertTrue(has_permission(auditor, "audit.read"))
        self.assertTrue(has_permission(auditor, "reporting.read"))

    def test_t2_require_permission_denies_auditor_write(self):
        with self.assertRaises(PermissionDeniedError) as err:
            require_permission(ctx("auditor"), "asset.write")
        self.assertEqual(str(err.exception), _DENY_MESSAGE)

    def test_t3_require_permission_allows_admin_and_supervisor(self):
        require_permission(ctx("admin"), "asset.write")
        require_permission(ctx("supervisor"), "workorder.close")

    def test_t4_purchasing_does_not_automatically_approve(self):
        self.assertFalse(has_permission(ctx("purchasing"), "purchase.approve"))
        for role in KNOWN_ROLES:
            self.assertNotIn("purchase.approve", BASE_PERMISSIONS[role])

    def test_t5_explicit_approver_grant_works(self):
        self.assertTrue(
            has_permission(
                ctx("purchasing"),
                "purchase.approve",
                explicit_grants=["purchase.approve"],
            )
        )
        self.assertTrue(
            has_permission(
                ctx("supervisor"),
                "purchase.approve",
                explicit_grants=["purchase.approve"],
            )
        )
        self.assertFalse(has_permission(ctx("technician"), "purchase.approve"))

    def test_t6_effective_permissions_unions_and_validates(self):
        result = effective_permissions(
            "supervisor", explicit_grants=["purchase.approve"]
        )
        self.assertIn("asset.write", result)
        self.assertIn("purchase.approve", result)
        self.assertIsInstance(result, frozenset)
        with self.assertRaises(ValidationError):
            effective_permissions("nobody")

    def test_t7_require_role_allows_and_denies(self):
        require_role(ctx("admin"), "admin")
        require_role(ctx("admin"), ["admin", "supervisor"])
        require_role(ctx("supervisor"), ["admin", "supervisor"])
        with self.assertRaises(PermissionDeniedError):
            require_role(ctx("technician"), ["admin", "supervisor"])
        with self.assertRaises(PermissionDeniedError):
            require_role(ctx("auditor"), "admin")

    def test_t8_assert_not_self_approval(self):
        admin = StubContext("admin", "user-1")
        with self.assertRaises(PermissionDeniedError) as err:
            assert_not_self_approval(admin, "user-1")
        self.assertEqual(str(err.exception), "self-approval is not permitted")
        assert_not_self_approval(admin, "user-2")

    def test_t9_known_roles_and_base_permissions_shape(self):
        self.assertEqual(
            KNOWN_ROLES,
            frozenset(
                {"admin", "supervisor", "technician", "purchasing", "auditor"}
            ),
        )
        for role in KNOWN_ROLES:
            self.assertIn(role, BASE_PERMISSIONS)
            self.assertIsInstance(BASE_PERMISSIONS[role], frozenset)
            self.assertGreater(len(BASE_PERMISSIONS[role]), 0)

    def test_t10_explicit_grant_allows_and_messages_identical(self):
        self.assertTrue(
            has_permission(
                ctx("admin"),
                PURCHASE_APPROVE_PERMISSION,
                explicit_grants=[PURCHASE_APPROVE_PERMISSION],
            )
        )
        with self.assertRaises(PermissionDeniedError) as require_perm_err:
            require_permission(ctx("auditor"), "asset.write")
        with self.assertRaises(PermissionDeniedError) as require_role_err:
            require_role(ctx("technician"), ["admin", "supervisor"])
        self.assertEqual(
            str(require_perm_err.exception), str(require_role_err.exception)
        )
        self.assertEqual(str(require_perm_err.exception), _DENY_MESSAGE)


if __name__ == "__main__":
    unittest.main()
