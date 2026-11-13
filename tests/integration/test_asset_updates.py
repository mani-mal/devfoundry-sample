"""Integration tests (T020): optimistic-concurrency asset version updates.

These tests apply the REAL shipped migrations to a temporary file database and
then exercise :func:`opsledger.assets.update_asset` and
:data:`opsledger.assets.updates.STALE_VERSION_MESSAGE` against that migrated
schema — no CREATE TABLE anywhere in the test, mirroring the
migrate-a-temp-db setup style. Acceptance (spec M3/T020): second writer with
stale version gets 409; first change retained.
"""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError
from opsledger.core.migrations import migrate
from opsledger.assets import create_asset, create_site
from opsledger.assets.updates import STALE_VERSION_MESSAGE, update_asset


class AssetUpdateTests(unittest.TestCase):
    """Integration tests for update_asset on the real migrated schema."""

    def _open_migrated(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda: connect(tmp.name).close())
        conn = connect(tmp.name)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def _seed_organizations(self, conn):
        created_text = "2026-11-06T12:00:00Z"
        with conn:
            conn.execute(
                "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                ("org-aaa", "org-aaa", "Organization AAA", created_text),
            )
            conn.execute(
                "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                ("org-bbb", "org-bbb", "Organization BBB", created_text),
            )

    def _context(self, organization_id):
        return OrganizationContext(organization_id=organization_id)

    def _seed_sites(self, conn):
        clock = FixedClock(datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc))
        self._seed_organizations(conn)
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

    def _seed_asset(self, conn, tag="pump-001"):
        clock = FixedClock(datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc))
        site_a, _ = self._seed_sites(conn)
        asset = create_asset(
            conn,
            self._context("org-aaa"),
            site_id=site_a["id"],
            tag=tag,
            name="Asset " + tag,
            criticality="medium",
            purchase_cost_cents=10000,
            clock=clock,
        )
        return asset

    def test_t1_two_writer_race_stale_version_gets_conflict(self):
        conn = self._open_migrated()
        asset = self._seed_asset(conn)
        self.assertEqual(1, asset["version"])
        writer1_field = "Rebuilt pump A"
        writer2_field = "Renamed by writer 2"

        winner = update_asset(
            conn,
            self._context("org-aaa"),
            asset_id=asset["id"],
            expected_version=1,
            name=writer1_field,
            clock=FixedClock(datetime(2026, 11, 13, 15, 0, 0, tzinfo=timezone.utc)),
        )
        self.assertEqual(2, winner["version"])
        self.assertEqual(writer1_field, winner["name"])

        with self.assertRaises(ConflictError) as caught:
            update_asset(
                conn,
                self._context("org-aaa"),
                asset_id=asset["id"],
                expected_version=1,
                name=writer2_field,
                clock=FixedClock(datetime(2026, 11, 13, 15, 1, 0, tzinfo=timezone.utc)),
            )
        self.assertEqual(STALE_VERSION_MESSAGE, caught.exception.args[0])

        refetched = conn.execute(
            "SELECT name, version FROM assets WHERE id = ?", (asset["id"],)
        ).fetchone()
        self.assertEqual(writer1_field, refetched["name"])
        self.assertNotEqual(writer2_field, refetched["name"])
        self.assertEqual(2, refetched["version"])

    def test_t2_sequential_updates_with_current_version(self):
        conn = self._open_migrated()
        asset = self._seed_asset(conn, tag="pump-002")
        first = update_asset(
            conn,
            self._context("org-aaa"),
            asset_id=asset["id"],
            expected_version=1,
            name="Renamed once",
            clock=FixedClock(datetime(2026, 11, 13, 15, 0, 0, tzinfo=timezone.utc)),
        )
        self.assertEqual(2, first["version"])
        self.assertEqual("Renamed once", first["name"])
        self.assertEqual(2, first["version"])
        self.assertEqual(2, first["version"])
        second = update_asset(
            conn,
            self._context("org-aaa"),
            asset_id=asset["id"],
            expected_version=2,
            criticality="high",
            clock=FixedClock(datetime(2026, 11, 13, 15, 5, 0, tzinfo=timezone.utc)),
        )
        self.assertEqual(3, second["version"])
        self.assertEqual("high", second["criticality"])
        self.assertEqual("Renamed once", second["name"])
        self.assertEqual(3, second["version"])
        self.assertEqual(3, second["version"])

    def test_t3_partial_updates_keep_stored_values(self):
        conn = self._open_migrated()
        asset = self._seed_asset(conn, tag="pump-003")
        self.assertEqual("medium", asset["criticality"])
        self.assertEqual(10000, asset["purchase_cost_cents"])

        name_only = update_asset(
            conn,
            self._context("org-aaa"),
            asset_id=asset["id"],
            expected_version=1,
            name="Only name changed",
            clock=FixedClock(datetime(2026, 11, 13, 15, 0, 0, tzinfo=timezone.utc)),
        )
        self.assertEqual("medium", name_only["criticality"])
        self.assertEqual(10000, name_only["purchase_cost_cents"])

        criticality_only = update_asset(
            conn,
            self._context("org-aaa"),
            asset_id=asset["id"],
            expected_version=2,
            criticality="low",
            clock=FixedClock(datetime(2026, 11, 13, 15, 5, 0, tzinfo=timezone.utc)),
        )
        self.assertEqual("low", criticality_only["criticality"])
        self.assertEqual("Only name changed", criticality_only["name"])
        self.assertEqual(10000, criticality_only["purchase_cost_cents"])

        cost_only = update_asset(
            conn,
            self._context("org-aaa"),
            asset_id=asset["id"],
            expected_version=3,
            criticality=None,
            purchase_cost_cents=25000,
            clock=FixedClock(datetime(2026, 11, 13, 15, 10, 0, tzinfo=timezone.utc)),
        )
        self.assertEqual(25000, cost_only["purchase_cost_cents"])
        self.assertEqual("Only name changed", cost_only["name"])
        self.assertEqual("low", cost_only["criticality"])
        self.assertEqual(4, cost_only["version"])

    def test_t4_updated_at_changes_on_update(self):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        created_instant = now - timedelta(days=3)
        updated_instant = now
        conn = self._open_migrated()
        asset = self._seed_asset(conn, tag="pump-004")
        stale_row = conn.execute(
            "SELECT created_at, updated_at FROM assets WHERE id = ?", (asset["id"],)
        ).fetchone()
        self.assertEqual(stale_row["created_at"], stale_row["updated_at"])
        updated = update_asset(
            conn,
            self._context("org-aaa"),
            asset_id=asset["id"],
            expected_version=1,
            name="Timestamped rename",
            clock=FixedClock(updated_instant),
        )
        self.assertNotEqual(asset["created_at"], updated["updated_at"])

    def test_t5_update_field_validation(self):
        conn = self._open_migrated()
        asset = self._seed_asset(conn, tag="pump-005")
        context = self._context("org-aaa")
        with self.assertRaises(ValidationError):
            update_asset(
                conn,
                context,
                asset_id=asset["id"],
                expected_version=0,
                name="Zero version",
                clock=FixedClock(datetime(2026, 11, 13, 15, 0, 0, tzinfo=timezone.utc)),
            )
        with self.assertRaises(ValidationError):
            update_asset(
                conn,
                context,
                asset_id=asset["id"],
                expected_version=-1,
                name="Negative version",
                clock=FixedClock(datetime(2026, 11, 13, 15, 0, 0, tzinfo=timezone.utc)),
            )
        with self.assertRaises(ValidationError):
            update_asset(
                conn,
                context,
                asset_id=asset["id"],
                expected_version=True,
                name="Bool version",
                clock=FixedClock(datetime(2026, 11, 13, 15, 0, 0, tzinfo=timezone.utc)),
            )
        with self.assertRaises(ValidationError):
            update_asset(
                conn,
                context,
                asset_id=asset["id"],
                expected_version=1,
                clock=FixedClock(datetime(2026, 11, 6, 0, 0, 0, tzinfo=timezone.utc)),
            )
        with self.assertRaises(ValidationError):
            update_asset(
                conn,
                context,
                asset_id=asset["id"],
                expected_version=1,
                criticality="urgent",
                clock=FixedClock(datetime(2026, 11, 6, 0, 0, 0, tzinfo=timezone.utc)),
            )
        with self.assertRaises(ValidationError):
            update_asset(
                conn,
                context,
                asset_id=asset["id"],
                expected_version=1,
                purchase_cost_cents=10000.5,
                clock=FixedClock(datetime(2026, 11, 6, 0, 0, 0, tzinfo=timezone.utc)),
            )

    def test_t6_cross_organization_no_leak_scoping(self):
        conn = self._open_migrated()
        asset = self._seed_asset(conn, tag="pump-005")
        context = self._context("org-aaa")
        nonexistent_id = "does-not-exist"
        with self.assertRaises(NotFoundError) as caught:
            update_asset(
                conn,
                context,
                asset_id=nonexistent_id,
                expected_version=1,
                criticality="low",
                clock=FixedClock(datetime(2026, 11, 13, 15, 1, 0, tzinfo=timezone.utc)),
            )
        self.assertEqual("asset not found", caught.exception.args[0])
        cross_org_context = OrganizationContext(organization_id="org-bbb")
        with self.assertRaises(NotFoundError) as caught:
            update_asset(
                conn,
                cross_org_context,
                asset_id=asset["id"],
                expected_version=1,
                criticality="low",
                clock=FixedClock(datetime(2026, 11, 13, 15, 2, 0, tzinfo=timezone.utc)),
            )
        self.assertEqual("asset not found", caught.exception.args[0])
