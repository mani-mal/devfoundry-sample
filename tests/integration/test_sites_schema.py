"""Integration tests (T017 part B): sites storage on the real migrated schema.

These tests apply the REAL shipped migrations to a temporary file database and
then exercise the sites module against that migrated schema — no CREATE TABLE
anywhere in the test, mirroring the migrate-a-temp-db style.
"""

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone

from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect, transaction
from opsledger.core.errors import ConflictError, NotFoundError
from opsledger.core.migrations import migrate
from opsledger.assets import (
    DUPLICATE_SITE_CODE_MESSAGE,
    SITE_NOT_FOUND_MESSAGE,
    create_site,
    get_site,
    list_sites,
)


class SitesSchemaTests(unittest.TestCase):
    """Integration tests against the real shipped migrations."""

    def _open_migrated(self) -> sqlite3.Connection:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda: connect(tmp.name).close())
        conn = connect(tmp.name)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def _seed_organizations(self, conn: sqlite3.Connection) -> None:
        created_text = "2026-11-06T12:00:00Z"
        with transaction(conn) as tx:
            tx.execute(
                "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                ("org-aaa", "org-aaa", "Organization AAA", created_text),
            )
            tx.execute(
                "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                ("org-bbb", "org-bbb", "Organization BBB", created_text),
            )

    def _context(self, organization_id: str) -> OrganizationContext:
        return OrganizationContext(organization_id=organization_id)

    def test_t1_sites_table_has_all_eight_columns(self):
        conn = self._open_migrated()
        info = conn.execute("PRAGMA table_info(sites)").fetchall()
        columns = [row[1] for row in info]
        self.assertEqual(
            [
                "id",
                "organization_id",
                "code",
                "name",
                "timezone",
                "created_at",
                "archived_at",
            ],
            columns,
        )
        unique_indexes = [
            row[1]
            for row in conn.execute("PRAGMA index_list(sites)").fetchall()
            if row[2]
        ]
        unique_column_sets = {
            tuple(
                info[0]
                for info in conn.execute(
                    "SELECT name FROM pragma_index_info(?) ORDER BY seqno",
                    (index_name,),
                ).fetchall()
            )
            for index_name in unique_indexes
        }
        self.assertIn(("organization_id", "code"), unique_column_sets)

    def test_t2_create_site_succeeds_against_real_migrated_schema(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        clock = FixedClock(datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc))
        first = create_site(
            conn,
            self._context("org-aaa"),
            code="main-plant",
            name="Main Plant",
            clock=clock,
        )
        self.assertEqual("main-plant", first["code"])
        self.assertEqual("UTC", first["timezone"])
        second = create_site(
            conn,
            self._context("org-bbb"),
            code="main-plant",
            name="Main Plant B",
            clock=clock,
        )
        self.assertEqual("main-plant", second["code"])
        self.assertNotEqual(first["id"], second["id"])
        with self.assertRaises(ConflictError) as ctx:
            create_site(
                conn,
                self._context("org-aaa"),
                code="main-plant",
                name="Main Plant Dup",
                clock=clock,
            )
        self.assertEqual(DUPLICATE_SITE_CODE_MESSAGE, str(ctx.exception))

    def test_t3_get_and_list_are_scope_limited_without_existence_leak(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        clock = FixedClock(datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc))
        cross = create_site(
            conn,
            self._context("org-bbb"),
            code="main-plant",
            name="Main Plant B",
            clock=clock,
        )
        own = create_site(
            conn,
            self._context("org-aaa"),
            code="depot-west",
            name="Depot West",
            clock=clock,
        )
        with self.assertRaises(NotFoundError) as cross_ctx:
            get_site(
                conn,
                self._context("org-aaa"),
                site_id=cross["id"],
            )
        with self.assertRaises(NotFoundError) as missing_ctx:
            get_site(
                conn,
                self._context("org-aaa"),
                site_id="site-nonexistent",
            )
        self.assertEqual(SITE_NOT_FOUND_MESSAGE, str(cross_ctx.exception))
        self.assertEqual(SITE_NOT_FOUND_MESSAGE, str(missing_ctx.exception))
        self.assertEqual(SITE_NOT_FOUND_MESSAGE, "site not found")
        rows = list_sites(conn, self._context("org-aaa"))
        self.assertEqual(1, len(rows))
        self.assertEqual("depot-west", rows[0]["code"])
        self.assertEqual("org-aaa", rows[0]["organization_id"])
        cross_rows = list_sites(conn, self._context("org-bbb"))
        self.assertEqual(1, len(cross_rows))
        self.assertEqual(cross["id"], cross_rows[0]["id"])
