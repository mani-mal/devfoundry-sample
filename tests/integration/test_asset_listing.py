"""Integration tests (T019): asset filtered list with stable pagination.

These tests apply the REAL shipped migrations to a temporary file database and
then exercise :func:`opsledger.assets.list_assets` against that migrated
schema — no CREATE TABLE anywhere in the test, mirroring the
migrate-a-temp-db setup style. Acceptance (spec M3/T019): identical
timestamps neither duplicate nor omit stable rows across pages.
"""

import tempfile
import unittest
from datetime import datetime, timezone

from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect, transaction
from opsledger.core.errors import ValidationError
from opsledger.core.migrations import migrate
from opsledger.assets import create_asset, create_site
from opsledger.assets.listing import asset_page_cursor, list_assets


class AssetListingTests(unittest.TestCase):
    """Integration tests for list_assets on the real migrated schema."""

    def _open_migrated(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda: connect(tmp.name).close())
        conn = connect(tmp.name)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def _seed_organizations(self, conn):
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

    def test_t1_stable_pagination_with_identical_timestamps(self):
        conn = self._open_migrated()
        site_a, _ = self._seed_sites(conn)
        clock = FixedClock(datetime(2026, 11, 13, 15, 0, 0, tzinfo=timezone.utc))
        expected_ids = []
        for i in range(1, 8):
            asset = create_asset(
                conn,
                self._context("org-aaa"),
                site_id=site_a["id"],
                tag="pump-" + str(i).zfill(3),
                name="Pump " + str(i).zfill(3),
                criticality="medium",
                purchase_cost_cents=10000 * i,
                clock=clock,
            )
            expected_ids.append(asset["id"])

        page1 = list_assets(conn, self._context("org-aaa"), limit=3)
        self.assertEqual(3, len(page1))
        cursor = asset_page_cursor(page1[-1])
        page2 = list_assets(conn, self._context("org-aaa"), limit=3, **cursor)
        self.assertEqual(3, len(page2))
        cursor = asset_page_cursor(page2[-1])
        page3 = list_assets(conn, self._context("org-aaa"), limit=3, **cursor)
        self.assertEqual(1, len(page3))

        collected = []
        for page in (page1, page2, page3):
            keys = [(row["created_at"], row["id"]) for row in page]
            self.assertEqual(sorted(keys), keys)
            for row in page:
                self.assertEqual("2026-11-13T15:00:00Z", row["created_at"])
                collected.append(row["id"])

        self.assertEqual(7, len(collected))
        self.assertEqual(7, len(set(collected)))
        self.assertEqual(set(expected_ids), set(collected))

    def test_t2_pagination_stable_across_repeated_runs(self):
        conn = self._open_migrated()
        site_a, _ = self._seed_sites(conn)
        clock = FixedClock(datetime(2026, 11, 13, 15, 0, 0, tzinfo=timezone.utc))
        for i in range(1, 8):
            create_asset(
                conn,
                self._context("org-aaa"),
                site_id=site_a["id"],
                tag="pump-" + str(i).zfill(3),
                name="Pump " + str(i).zfill(3),
                criticality="low",
                purchase_cost_cents=10000,
                clock=clock,
            )

        def paginate_all():
            pages = []
            page = list_assets(conn, self._context("org-aaa"), limit=3)
            pages.append([row["id"] for row in page])
            while page:
                cursor = asset_page_cursor(page[-1])
                page = list_assets(conn, self._context("org-aaa"), limit=3, **cursor)
                if page:
                    pages.append([row["id"] for row in page])
            return pages

        self.assertEqual(paginate_all(), paginate_all())

    def test_t3_filters_criticality_site_and_archived(self):
        conn = self._open_migrated()
        site_a, _ = self._seed_sites(conn)
        east_clock = FixedClock(datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc))
        site_east = create_site(
            conn,
            self._context("org-aaa"),
            code="east",
            name="Site East",
            clock=east_clock,
        )
        clock = FixedClock(datetime(2026, 11, 13, 15, 0, 0, tzinfo=timezone.utc))

        def create(tag, site, criticality):
            return create_asset(
                conn,
                self._context("org-aaa"),
                site_id=site["id"],
                tag=tag,
                name="Asset " + tag,
                criticality=criticality,
                purchase_cost_cents=10000,
                clock=clock,
            )

        high = create("pump-001", site_a, "high")
        low_site_main = create("pump-002", site_a, "low")
        low_site_east = create("pump-003", site_east, "low")

        only_high = list_assets(conn, self._context("org-aaa"), criticality="high")
        self.assertEqual(1, len(only_high))
        self.assertEqual("high", only_high[0]["criticality"])
        self.assertEqual(high["id"], only_high[0]["id"])

        only_east = list_assets(conn, self._context("org-aaa"), site_id=site_east["id"])
        self.assertEqual(1, len(only_east))
        self.assertEqual(site_east["id"], only_east[0]["site_id"])
        self.assertEqual(low_site_east["id"], only_east[0]["id"])

        archived_text = "2026-11-13T16:00:00Z"
        with transaction(conn) as tx:
            tx.execute(
                "UPDATE assets SET archived_at = ? WHERE id = ?",
                (archived_text, low_site_main["id"]),
            )

        default_visible = list_assets(conn, self._context("org-aaa"))
        self.assertEqual(2, len(default_visible))
        self.assertFalse(any(row["id"] == low_site_main["id"] for row in default_visible))

        with_archived = list_assets(conn, self._context("org-aaa"), include_archived=True)
        self.assertEqual(3, len(with_archived))
        self.assertTrue(any(row["id"] == low_site_main["id"] for row in with_archived))
        archived_row = [
            row for row in with_archived if row["id"] == low_site_main["id"]
        ][0]
        self.assertEqual(archived_text, archived_row["archived_at"])

    def test_t4_organization_scoping(self):
        conn = self._open_migrated()
        site_a, site_b = self._seed_sites(conn)
        clock = FixedClock(datetime(2026, 11, 13, 15, 0, 0, tzinfo=timezone.utc))
        cross_org = create_asset(
            conn,
            self._context("org-bbb"),
            site_id=site_b["id"],
            tag="shared-tag",
            name="Asset BBB",
            criticality="medium",
            purchase_cost_cents=10000,
            clock=clock,
        )
        owned_org = create_asset(
            conn,
            self._context("org-aaa"),
            site_id=site_a["id"],
            tag="shared-tag",
            name="Asset AAA",
            criticality="medium",
            purchase_cost_cents=10000,
            clock=clock,
        )

        listed = list_assets(conn, self._context("org-aaa"))
        self.assertEqual(1, len(listed))
        self.assertEqual("org-aaa", listed[0]["organization_id"])
        self.assertEqual(owned_org["id"], listed[0]["id"])
        self.assertNotEqual(cross_org["id"], listed[0]["id"])

        reverse = list_assets(conn, self._context("org-bbb"))
        self.assertEqual(1, len(reverse))
        self.assertEqual("org-bbb", reverse[0]["organization_id"])
        self.assertEqual(cross_org["id"], reverse[0]["id"])
        self.assertNotEqual(owned_org["id"], reverse[0]["id"])

    def test_t5_limit_validation(self):
        conn = self._open_migrated()
        site_a, _ = self._seed_sites(conn)
        clock = FixedClock(datetime(2026, 11, 13, 15, 0, 0, tzinfo=timezone.utc))
        create_asset(
            conn,
            self._context("org-aaa"),
            site_id=site_a["id"],
            tag="pump-001",
            name="Asset 001",
            criticality="low",
            purchase_cost_cents=10000,
            clock=clock,
        )

        with self.assertRaises(ValidationError):
            list_assets(conn, self._context("org-aaa"), limit=0)
        with self.assertRaises(ValidationError):
            list_assets(conn, self._context("org-aaa"), limit=201)

        single = list_assets(conn, self._context("org-aaa"), limit=1)
        self.assertEqual(1, len(single))
        full = list_assets(conn, self._context("org-aaa"), limit=200)
        self.assertEqual(1, len(full))

    def test_t6_cursor_and_criticality_validation(self):
        conn = self._open_migrated()
        site_a, _ = self._seed_sites(conn)
        clock = FixedClock(datetime(2026, 11, 13, 15, 0, 0, tzinfo=timezone.utc))
        asset = create_asset(
            conn,
            self._context("org-aaa"),
            site_id=site_a["id"],
            tag="pump-001",
            name="Asset 001",
            criticality="low",
            purchase_cost_cents=10000,
            clock=clock,
        )

        with self.assertRaises(ValidationError):
            list_assets(
                conn,
                self._context("org-aaa"),
                limit=10,
                after_created_at=asset["created_at"],
            )
        with self.assertRaises(ValidationError):
            list_assets(conn, self._context("org-aaa"), limit=10, after_id=asset["id"])
        with self.assertRaises(ValidationError):
            list_assets(conn, self._context("org-aaa"), limit=10, criticality="urgent")

    def test_t7_empty_result(self):
        conn = self._open_migrated()
        _, site_b = self._seed_sites(conn)
        clock = FixedClock(datetime(2026, 11, 13, 15, 0, 0, tzinfo=timezone.utc))
        asset = create_asset(
            conn,
            self._context("org-bbb"),
            site_id=site_b["id"],
            tag="pump-001",
            name="Asset BBB",
            criticality="low",
            purchase_cost_cents=10000,
            clock=clock,
        )

        self.assertEqual([], list_assets(conn, self._context("org-aaa")))

        cursor = asset_page_cursor(asset)
        self.assertEqual(
            [],
            list_assets(
                conn,
                self._context("org-bbb"),
                limit=10,
                after_created_at=cursor["after_created_at"],
                after_id=cursor["after_id"],
            ),
        )
