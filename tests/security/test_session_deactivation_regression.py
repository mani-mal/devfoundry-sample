"""T075 (part 1) session deactivation regression: deactivation vs live sessions.

Deactivating a membership DELETES the memberships row immediately (T014),
so every authorization check loses access right away -- but the sessions
row is NOT auto-revoked: resolve_session still returns the joined row for
the user's token and site_memberships grants are independent of the
deletion. Access is lost because every check reads current membership
state, not because sessions die; only an explicit logout revokes the
session. The org-scoping and further deactivation cases are a separate
follow-up task that ADDS methods to this file.
"""

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from opsledger.assets import create_asset, create_site
from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect, transaction
from opsledger.core.errors import ValidationError
from opsledger.core.migrations import migrate
from opsledger.identity import provision_user
from opsledger.identity.sites import active_site_ids, deactivate_membership
from opsledger.identity.service import login, logout, resolve_session
from opsledger.reporting.dashboard import dashboard

TEST_USER_ID = "usr-deact"
TEST_EMAIL = "deact@example.com"
TEST_PASSWORD = "correct horse battery staple"


def _at(seconds: int) -> FixedClock:
    return FixedClock(
        datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    )


class SessionDeactivationRegressionTests(unittest.TestCase):
    """Regression coverage for immediate membership deactivation (T075 part 1)."""

    def _open_migrated(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda p=tmp.name: os.path.exists(p) and os.unlink(p))
        self.addCleanup(lambda: connect(tmp.name).close())
        conn = connect(tmp.name)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def test_deactivated_membership_loses_access_but_session_needs_explicit_logout(self):
        class _UCtx:
            """Site membership context: organization_id + user_id attributes."""

            def __init__(self, organization_id, user_id):
                self.organization_id = organization_id
                self.user_id = user_id

        class _Actor:
            """Minimal authorization context: role/actor_id attributes."""

            def __init__(self, role, actor_id):
                self.role = role
                self.actor_id = actor_id

        conn = self._open_migrated()
        provision_user(
            conn,
            user_id=TEST_USER_ID,
            email=TEST_EMAIL,
            display_name="Deact",
            password=TEST_PASSWORD,
            clock=_at(0),
        )
        with transaction(conn) as tx:
            tx.execute(
                "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                ("org-a", "org-a", "Org A", "2026-11-06T12:00:00Z"),
            )
            tx.execute(
                "INSERT INTO memberships (organization_id, user_id, role, created_at)"
                " VALUES (?, ?, ?, ?)",
                ("org-a", TEST_USER_ID, "lead", "2026-11-06T12:00:00Z"),
            )
        org_ctx = OrganizationContext(organization_id="org-a", actor_id=TEST_USER_ID)
        site = create_site(conn, org_ctx, code="hq", name="Headquarters", clock=_at(1))
        create_asset(
            conn,
            org_ctx,
            site_id=site["id"],
            tag="pump-1",
            name="Pump 1",
            criticality="low",
            purchase_cost_cents=2500,
            clock=_at(2),
        )
        with transaction(conn) as tx:
            tx.execute(
                "INSERT INTO site_memberships"
                " (organization_id, site_id, user_id, granted_at, revoked_at)"
                " VALUES (?, ?, ?, ?, NULL)",
                ("org-a", site["id"], TEST_USER_ID, "2026-11-06T12:00:00Z"),
            )
        uctx = _UCtx("org-a", TEST_USER_ID)
        actor = _Actor("supervisor", TEST_USER_ID)
        with self.assertRaises(ValidationError) as raised:
            active_site_ids(conn, org_ctx)
        self.assertEqual("valid site membership context required", str(raised.exception))
        raw, _session_record, user_id = login(
            conn, email=TEST_EMAIL, password=TEST_PASSWORD, clock=_at(10)
        )
        self.assertEqual(TEST_USER_ID, user_id)
        self.assertEqual(1, dashboard(conn, org_ctx, actor=actor)["assets"]["total"])
        self.assertEqual([site["id"]], active_site_ids(conn, uctx))
        self.assertIsNotNone(resolve_session(conn, raw_token=raw, clock=_at(11)))
        deactivate_membership(
            conn, organization_id="org-a", user_id=TEST_USER_ID, clock=_at(20)
        )
        deactivate_membership(
            conn, organization_id="org-a", user_id=TEST_USER_ID, clock=_at(20)
        )
        count_sql = "SELECT COUNT(*) FROM memberships WHERE organization_id = ? AND user_id = ?"
        self.assertEqual(0, conn.execute(count_sql, ("org-a", TEST_USER_ID)).fetchone()[0])
        self.assertIsNotNone(resolve_session(conn, raw_token=raw, clock=_at(22)))
        role_sql = "SELECT role FROM memberships WHERE organization_id = ? AND user_id = ?"
        self.assertIsNone(conn.execute(role_sql, ("org-a", TEST_USER_ID)).fetchone())
        self.assertEqual([site["id"]], active_site_ids(conn, uctx))
        logout(conn, raw_token=raw, clock=_at(30))
        self.assertIsNone(resolve_session(conn, raw_token=raw, clock=_at(31)))
        logout(conn, raw_token=raw, clock=_at(32))


if __name__ == "__main__":
    unittest.main()
