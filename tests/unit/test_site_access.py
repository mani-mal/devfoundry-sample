"""Unit tests for the site membership domain module (T014).

Covers the pure access predicates and the two DB helpers against real temp
SQLite databases. Migration 0002 defines the `memberships` shape:
organization_id/user_id/role/created_at with PK (organization_id, user_id);
the `site_memberships` table shape follows the module documentation.
"""

import os
import tempfile
import unittest
from datetime import datetime, timezone

from opsledger.core.clock import FixedClock
from opsledger.core.db import connect
from opsledger.core.errors import PermissionDeniedError, ValidationError
from opsledger.identity.sites import (
    SiteGrant,
    active_site_ids,
    deactivate_membership,
    has_site_access,
    revoke_site_grant,
    require_site_access,
    site_access_active,
)


class GrantLike:
    """Row-like grant object (not a SiteGrant) for defensive-read tests."""

    def __init__(self, organization_id, site_id, user_id, granted_at, revoked_at=None):
        self.organization_id = organization_id
        self.site_id = site_id
        self.user_id = user_id
        self.granted_at = granted_at
        self.revoked_at = revoked_at


class ContextLike:
    def __init__(self, organization_id, site_id=None, user_id=None):
        self.organization_id = organization_id
        self.site_id = site_id
        self.user_id = user_id


class SiteAccessTest(unittest.TestCase):
    def test_site_access_active_predicate(self):
        active = SiteGrant(
            organization_id="org-1",
            site_id="site-1",
            user_id="user-1",
            granted_at="2026-11-06T12:00:00Z",
        )
        revoked = GrantLike(
            "org-1", "site-1", "user-1", "2026-11-06T12:00:00Z", "2026-11-06T13:00:00Z"
        )
        self.assertTrue(site_access_active(active))
        self.assertTrue(site_access_active(GrantLike("org-1", "site-1", "user-1", "2026-11-06T12:00:00Z")))
        self.assertFalse(site_access_active(revoked))
        with self.assertRaises(ValidationError):
            site_access_active(object())

    def test_has_site_access_matches_org_and_site(self):
        grant = SiteGrant(
            organization_id="org-1",
            site_id="site-1",
            user_id="user-1",
            granted_at="2026-11-06T12:00:00Z",
        )
        other_site = GrantLike("org-1", "site-2", "user-1", "2026-11-06T12:00:00Z")
        other_org = GrantLike("org-2", "site-1", "user-1", "2026-11-06T12:00:00Z")
        revoked = GrantLike("org-1", "site-1", "user-1", "2026-11-06T12:00:00Z", "2026-11-06T13:00:00Z")
        self.assertTrue(has_site_access(ContextLike("org-1", site_id="site-1"), [grant]))
        self.assertFalse(has_site_access(ContextLike("org-1", site_id="site-1"), [other_site]))
        self.assertFalse(has_site_access(ContextLike("org-1", site_id="site-1"), [other_org]))
        self.assertFalse(has_site_access(ContextLike("org-1", site_id="site-1"), [revoked]))

    def test_require_site_access_raises_and_passes(self):
        grant = SiteGrant(
            organization_id="org-1",
            site_id="site-1",
            user_id="user-1",
            granted_at="2026-11-06T12:00:00Z",
        )
        other_site = GrantLike("org-1", "site-2", "user-1", "2026-11-06T12:00:00Z")
        other_org = GrantLike("org-2", "site-1", "user-1", "2026-11-06T12:00:00Z")
        revoked = GrantLike("org-1", "site-1", "user-1", "2026-11-06T12:00:00Z", "2026-11-06T13:00:00Z")
        for cases in ([other_site], [other_org], [revoked]):
            with self.assertRaises(PermissionDeniedError) as exc:
                require_site_access(ContextLike("org-1", site_id="site-1"), cases)
            self.assertEqual(str(exc.exception), "no access to this site")
        require_site_access(ContextLike("org-1", site_id="site-1"), [grant])

    def test_deactivation_is_immediate(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "sites.db")
            conn = connect(db_path)
            conn.execute(
                "CREATE TABLE memberships ("
                " organization_id TEXT NOT NULL,"
                " user_id TEXT NOT NULL,"
                " role TEXT NOT NULL,"
                " created_at TEXT NOT NULL,"
                " PRIMARY KEY (organization_id, user_id))"
            )
            conn.execute(
                "INSERT INTO memberships VALUES (?, ?, ?, ?)",
                ("org-1", "user-1", "developer", "2026-11-06T12:00:00Z"),
            )
            deactivate_membership(conn, organization_id="org-1", user_id="user-1", clock=None)
            rows = conn.execute(
                "SELECT * FROM memberships WHERE organization_id = ? AND user_id = ?",
                ("org-1", "user-1"),
            ).fetchall()
            self.assertEqual(len(rows), 0)

    def test_deactivate_missing_row_is_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "sites.db")
            conn = connect(db_path)
            conn.execute(
                "CREATE TABLE memberships ("
                " organization_id TEXT NOT NULL,"
                " user_id TEXT NOT NULL,"
                " role TEXT NOT NULL,"
                " created_at TEXT NOT NULL,"
                " PRIMARY KEY (organization_id, user_id))"
            )
            deactivate_membership(conn, organization_id="org-9", user_id="user-9", clock=None)
            rows = conn.execute("SELECT * FROM memberships").fetchall()
            self.assertEqual(len(rows), 0)

    def test_revoke_site_grant_sets_revoked_at(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "sites.db")
            conn = connect(db_path)
            conn.execute(
                "CREATE TABLE site_memberships ("
                " organization_id TEXT NOT NULL,"
                " site_id TEXT NOT NULL,"
                " user_id TEXT NOT NULL,"
                " granted_at TEXT NOT NULL,"
                " revoked_at TEXT,"
                " PRIMARY KEY (organization_id, site_id, user_id))"
            )
            conn.execute(
                "INSERT INTO site_memberships VALUES (?, ?, ?, ?, NULL)",
                ("org-1", "site-1", "user-1", "2026-11-06T12:00:00Z"),
            )
            clock = FixedClock(datetime(2026, 11, 13, 10, 0, 0, tzinfo=timezone.utc))
            grant = SiteGrant(
                organization_id="org-1",
                site_id="site-1",
                user_id="user-1",
                granted_at="2026-11-06T12:00:00Z",
            )
            revoke_site_grant(conn, grant=grant, clock=clock)
            rows = conn.execute(
                "SELECT revoked_at FROM site_memberships"
                " WHERE organization_id = ? AND site_id = ? AND user_id = ?",
                ("org-1", "site-1", "user-1"),
            ).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["revoked_at"], "2026-11-13T10:00:00Z")
            revoke_site_grant(conn, grant=grant, clock=clock)
            rows_after = conn.execute(
                "SELECT revoked_at FROM site_memberships"
                " WHERE organization_id = ? AND site_id = ? AND user_id = ?",
                ("org-1", "site-1", "user-1"),
            ).fetchall()
            self.assertEqual(rows_after[0]["revoked_at"], "2026-11-13T10:00:00Z")

    def test_active_site_ids_returns_unrevoked(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "sites.db")
            conn = connect(db_path)
            conn.execute(
                "CREATE TABLE site_memberships ("
                " organization_id TEXT NOT NULL,"
                " site_id TEXT NOT NULL,"
                " user_id TEXT NOT NULL,"
                " granted_at TEXT NOT NULL,"
                " revoked_at TEXT,"
                " PRIMARY KEY (organization_id, site_id, user_id))"
            )
            conn.execute(
                "INSERT INTO site_memberships VALUES (?, ?, ?, ?, NULL)",
                ("org-1", "site-1", "user-1", "2026-11-06T12:00:00Z"),
            )
            conn.execute(
                "INSERT INTO site_memberships VALUES (?, ?, ?, ?, NULL)",
                ("org-1", "site-2", "user-1", "2026-11-06T12:00:00Z"),
            )
            conn.execute(
                "INSERT INTO site_memberships VALUES (?, ?, ?, ?, ?)",
                ("org-1", "site-3", "user-1", "2026-11-06T12:00:00Z", "2026-11-13T09:00:00Z"),
            )
            context = ContextLike("org-1", user_id="user-1")
            self.assertEqual(sorted(active_site_ids(conn, context)), ["site-1", "site-2"])

    def test_require_site_access_empty_grants_denies(self):
        with self.assertRaises(PermissionDeniedError) as exc:
            require_site_access(ContextLike("org-1", site_id="site-1"), [])
        self.assertEqual(str(exc.exception), "no access to this site")


if __name__ == "__main__":
    unittest.main()
