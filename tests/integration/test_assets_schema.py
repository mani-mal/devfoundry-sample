"""Integration tests (T018 part B): assets storage on the real migrated schema.

These tests apply the REAL shipped migrations to a temporary file database and
then exercise the assets module against that migrated schema — no CREATE TABLE
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
    DUPLICATE_ASSET_TAG_MESSAGE,
    create_asset,
    create_site,
)


class AssetsSchemaTests(unittest.TestCase):
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

    def _seed_sites(self, conn: sqlite3.Connection) -> tuple:
        clock = FixedClock(datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc))
        site_a = create_site(
            conn,
            self._context("org-aaa"),
            code="main",
            name="Site A",
            clock=clock,
        )
        site_b = create_site(
            conn,
            self._context("org-bbb"),
            code="main",
            name="Site B",
            clock=clock,
        )
        return site_a, site_b

    def test_t1_assets_table_has_all_eleven_columns(self):
        conn = self._open_migrated()
        info = conn.execute("PRAGMA table_info(assets)").fetchall()
        columns = [row[1] for row in info]
        self.assertEqual(
            [
                "id",
                "organization_id",
                "site_id",
                "tag",
                "name",
                "criticality",
                "purchase_cost_cents",
                "version",
                "created_at",
                "updated_at",
                "archived_at",
            ],
            columns,
        )

    def test_t2_create_asset_succeeds_against_real_migrated_schema(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        site_a, site_b = self._seed_sites(conn)
        clock = FixedClock(datetime(2026, 11, 13, 13, 0, 0, tzinfo=timezone.utc))
        first = create_asset(
            conn,
            self._context("org-aaa"),
            site_id=site_a["id"],
            tag="pump-001",
            name="Pump 001",
            criticality="medium",
            purchase_cost_cents=120000,
            clock=clock,
        )
        self.assertEqual(1, first["version"])
        self.assertIsNone(first["archived_at"])
        second = create_asset(
            conn,
            self._context("org-bbb"),
            site_id=site_b["id"],
            tag="pump-001",
            name="Pump 001 B",
            criticality="low",
            purchase_cost_cents=50000,
            clock=clock,
        )
        self.assertEqual(1, second["version"])
        self.assertNotEqual(first["id"], second["id"])
        with self.assertRaises(ConflictError) as ctx:
            create_asset(
                conn,
                self._context("org-aaa"),
                site_id=site_a["id"],
                tag="pump-001",
                name="Pump 001 Dup",
                criticality="high",
                purchase_cost_cents=1000,
                clock=clock,
            )
        self.assertEqual(DUPLICATE_ASSET_TAG_MESSAGE, str(ctx.exception))

    def test_t3_site_relationship_is_scoped_at_database_level(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        site_a, site_b = self._seed_sites(conn)
        with transaction(conn) as tx:
            with self.assertRaises(sqlite3.IntegrityError):
                tx.execute(
                    "INSERT INTO assets (id, organization_id, site_id, tag, name,"
                    " criticality, purchase_cost_cents, version, created_at,"
                    " updated_at, archived_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "ast-cross-org",
                        "org-aaa",
                        site_b["id"],
                        "pump-cross",
                        "Pump Cross",
                        "low",
                        100,
                        1,
                        "2026-11-13T12:00:00Z",
                        "2026-11-13T12:00:00Z",
                        None,
                    ),
                )
        with self.assertRaises(NotFoundError) as ctx:
            create_asset(
                conn,
                self._context("org-aaa"),
                site_id=site_b["id"],
                tag="pump-cross",
                name="Pump Cross",
                criticality="low",
                purchase_cost_cents=100,
                clock=FixedClock(datetime(2026, 11, 13, 14, 0, 0, tzinfo=timezone.utc)),
            )
        self.assertEqual("site not found", str(ctx.exception))

    def test_t4_check_constraints_refuse_invalid_values(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        site_a, _ = self._seed_sites(conn)
        base_sql = (
            "INSERT INTO assets (id, organization_id, site_id, tag, name,"
            " criticality, purchase_cost_cents, version, created_at,"
            " updated_at, archived_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        valid_row = (
            "ast-check",
            "org-aaa",
            site_a["id"],
            "pump-check",
            "Pump Check",
            "low",
            100,
            1,
            "2026-11-13T12:00:00Z",
            "2026-11-13T12:00:00Z",
            None,
        )
        with transaction(conn) as tx:
            with self.assertRaises(sqlite3.IntegrityError):
                tx.execute(base_sql, (*valid_row[:5], "urgent", *valid_row[6:]))
            with self.assertRaises(sqlite3.IntegrityError):
                tx.execute(base_sql, (*valid_row[:6], -1, *valid_row[7:]))
            with self.assertRaises(sqlite3.IntegrityError):
                tx.execute(base_sql, (*valid_row[:7], 0, *valid_row[8:]))
