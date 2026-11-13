"""Integration tests (T012): organization context isolation on the real migrated schema.

These tests apply the REAL shipped migrations to a temporary file database and
then exercise the organization context guards against that migrated schema --
no CREATE TABLE anywhere in the test.
"""

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone

from opsledger.core.clock import FixedClock
from opsledger.core.db import connect
from opsledger.core.errors import NotFoundError, ValidationError
from opsledger.core.migrations import migrate
from opsledger.core.context import (
    OrganizationContext,
    require_context,
    require_owned,
    scoped_all,
    scoped_first,
)


class ContextIsolationTests(unittest.TestCase):
    """Integration tests against the real shipped migrations."""

    def _open_migrated(self) -> sqlite3.Connection:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda: connect(tmp.name).close())
        conn = connect(tmp.name)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def setUp(self):
        self.conn = self._open_migrated()
        clock = FixedClock(datetime(2026, 11, 6, 12, 0, 0, tzinfo=timezone.utc))
        created_at = clock.timestamp()
        self.conn.execute(
            "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
            ("org-aaa", "org-aaa", "AAA Org", created_at),
        )
        self.conn.execute(
            "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
            ("org-bbb", "org-bbb", "BBB Org", created_at),
        )
        self.conn.execute(
            "INSERT INTO users (id, email, display_name, created_at) VALUES (?, ?, ?, ?)",
            ("u-aaa", "u-aaa@aaa.test", "User AAA", created_at),
        )
        self.conn.execute(
            "INSERT INTO users (id, email, display_name, created_at) VALUES (?, ?, ?, ?)",
            ("u-bbb", "u-bbb@bbb.test", "User BBB", created_at),
        )
        self.conn.execute(
            "INSERT INTO memberships (organization_id, user_id, role, created_at) VALUES (?, ?, ?, ?)",
            ("org-aaa", "u-aaa", "developer", created_at),
        )
        self.conn.execute(
            "INSERT INTO memberships (organization_id, user_id, role, created_at) VALUES (?, ?, ?, ?)",
            ("org-bbb", "u-bbb", "developer", created_at),
        )
        self.conn.commit()

    def test_t1_scoped_first_returns_own_org_row(self):
        ctx_a = OrganizationContext(organization_id="org-aaa")
        ctx_b = OrganizationContext(organization_id="org-bbb")
        sql = "SELECT *, id AS organization_id FROM organizations WHERE slug = ?"
        row_a = scoped_first(self.conn, ctx_a, sql, ("org-aaa",))
        self.assertEqual("org-aaa", row_a["slug"])
        row_b = scoped_first(self.conn, ctx_b, sql, ("org-bbb",))
        self.assertEqual("org-bbb", row_b["slug"])

    def test_t2_not_found_message_identical_no_leak(self):
        ctx_a = OrganizationContext(organization_id="org-aaa")
        sql = "SELECT *, id AS organization_id FROM organizations WHERE id = ?"
        with self.assertRaises(NotFoundError) as nonexistent:
            lookup = scoped_first(
                self.conn,
                ctx_a,
                sql,
                ("org-zzz",),
            )
            require_owned(ctx_a, lookup)
        with self.assertRaises(NotFoundError) as foreign:
            lookup = scoped_first(
                self.conn,
                ctx_a,
                sql,
                ("org-bbb",),
            )
            require_owned(ctx_a, lookup)
        self.assertEqual(
            nonexistent.exception.args[0], foreign.exception.args[0]
        )

    def test_t3_scoped_all_returns_only_in_scope_rows(self):
        ctx_a = OrganizationContext(organization_id="org-aaa")
        result = scoped_all(
            self.conn,
            ctx_a,
            "SELECT *, id AS organization_id FROM organizations ORDER BY id",
        )
        self.assertEqual(1, len(result))
        self.assertEqual("org-aaa", result[0]["slug"])

    def test_t4_rejects_bare_string_context(self):
        with self.assertRaises(ValidationError):
            require_context("org-aaa")

    def test_t5_memberships_are_scoped(self):
        ctx_a = OrganizationContext(organization_id="org-aaa")
        result = scoped_first(
            self.conn,
            ctx_a,
            "SELECT m.* FROM memberships m JOIN users u ON u.id = m.user_id WHERE u.id = ?",
            ("u-bbb",),
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
