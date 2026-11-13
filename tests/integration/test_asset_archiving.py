"""Integration tests (T021): site/asset archive rules.

These tests apply the REAL shipped migrations to a temporary file database and
then exercise :func:`opsledger.assets.archive_site`, :func:`archive_asset`,
:func:`unarchive_site`, :func:`unarchive_asset`, :func:`require_site_accepts_assets`,
:data:`SITE_HAS_LIVE_ASSETS_MESSAGE` and :data:`ARCHIVED_SITE_MESSAGE` against
the migrated schema — no CREATE TABLE anywhere in the test, mirroring the
migrate-a-temp-db setup style. Acceptance (spec M3/T021): referenced records
retained; archived objects cannot accept new work.
"""

import tempfile
import unittest
from datetime import datetime, timezone

from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError
from opsledger.core.migrations import migrate
from opsledger.assets import (
    ARCHIVED_SITE_MESSAGE,
    SITE_HAS_LIVE_ASSETS_MESSAGE,
    list_assets,
    list_sites,
)
from opsledger.assets.archiving import (
    archive_asset,
    archive_site,
    require_site_accepts_assets,
    unarchive_asset,
    unarchive_site,
)
from opsledger.assets.assets import create_asset
from opsledger.assets.sites import create_site


class AssetArchivingTests(unittest.TestCase):
    """Integration tests for archive_site/archive_asset on the migrated schema."""

    def _open_migrated(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda: connect(tmp.name).close())
        conn = connect(tmp.name)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def _insert_organization(self, conn, identifier="org-aaa"):
        with conn:
            conn.execute(
                "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                (identifier, identifier, "Organization " + identifier, "2026-11-06T12:00:00Z"),
            )

    def _context(self, organization_id):
        return OrganizationContext(organization_id=organization_id)

    def _clock(self, hour=12):
        return FixedClock(datetime(2026, 11, 13, hour, 0, 0, tzinfo=timezone.utc))

    def test_t1_archive_retains_both_rows(self):
        conn = self._open_migrated()
        self._insert_organization(conn)
        site = create_site(
            conn, self._context("org-aaa"), code="main", name="Site A", clock=self._clock()
        )
        asset = create_asset(
            conn,
            self._context("org-aaa"),
            site_id=site["id"],
            tag="pump-001",
            name="Pump 001",
            criticality="medium",
            purchase_cost_cents=10000,
            clock=self._clock(),
        )
        archived_asset = archive_asset(
            conn, self._context("org-aaa"), asset_id=asset["id"], clock=self._clock(13)
        )
        self.assertIsNotNone(archived_asset["archived_at"])
        self.assertRegex(archived_asset["archived_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        archived_site = archive_site(
            conn, self._context("org-aaa"), site_id=site["id"], clock=self._clock(14)
        )
        self.assertIsNotNone(archived_site["archived_at"])
        self.assertRegex(archived_site["archived_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0])
        self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0])

    def test_t2_live_assets_guard_keeps_site_live(self):
        conn = self._open_migrated()
        self._insert_organization(conn)
        site = create_site(
            conn, self._context("org-aaa"), code="main", name="Site A", clock=self._clock()
        )
        asset = create_asset(
            conn,
            self._context("org-aaa"),
            site_id=site["id"],
            tag="pump-001",
            name="Pump 001",
            criticality="medium",
            purchase_cost_cents=10000,
            clock=self._clock(),
        )
        with self.assertRaises(ConflictError) as caught:
            archive_site(
                conn, self._context("org-aaa"), site_id=site["id"], clock=self._clock(13)
            )
        self.assertEqual(SITE_HAS_LIVE_ASSETS_MESSAGE, caught.exception.args[0])
        refetched = conn.execute(
            "SELECT archived_at FROM sites WHERE id = ?", (site["id"],)
        ).fetchone()
        self.assertIsNone(refetched["archived_at"])
        blocking = conn.execute(
            "SELECT id, archived_at FROM assets WHERE id = ?", (asset["id"],)
        ).fetchone()
        self.assertEqual(asset["id"], blocking["id"])
        self.assertIsNone(blocking["archived_at"])

    def test_t3_archived_site_guard_rejects_new_work(self):
        conn = self._open_migrated()
        self._insert_organization(conn)
        site = create_site(
            conn, self._context("org-aaa"), code="main", name="Site A", clock=self._clock()
        )
        live_row = require_site_accepts_assets(site)
        self.assertIsNone(live_row)
        archived_row = archive_site(
            conn, self._context("org-aaa"), site_id=site["id"], clock=self._clock(13)
        )
        with self.assertRaises(ConflictError) as caught:
            require_site_accepts_assets(archived_row)
        self.assertEqual(ARCHIVED_SITE_MESSAGE, caught.exception.args[0])
        with self.assertRaises(ValidationError):
            require_site_accepts_assets(object())

    def test_t4_archived_excluded_from_default_lists(self):
        conn = self._open_migrated()
        self._insert_organization(conn)
        site_kept = create_site(
            conn, self._context("org-aaa"), code="kept", name="Kept Site", clock=self._clock()
        )
        site_archived = create_site(
            conn,
            self._context("org-aaa"),
            code="gone",
            name="Archived Site",
            clock=self._clock(),
        )
        asset_kept = create_asset(
            conn,
            self._context("org-aaa"),
            site_id=site_kept["id"],
            tag="pump-001",
            name="Kept Pump",
            criticality="medium",
            purchase_cost_cents=10000,
            clock=self._clock(),
        )
        asset_archived = create_asset(
            conn,
            self._context("org-aaa"),
            site_id=site_kept["id"],
            tag="pump-002",
            name="Archived Pump",
            criticality="medium",
            purchase_cost_cents=10000,
            clock=self._clock(),
        )
        archive_asset(
            conn, self._context("org-aaa"), asset_id=asset_archived["id"], clock=self._clock(13)
        )
        archive_site(
            conn, self._context("org-aaa"), site_id=site_archived["id"], clock=self._clock(14)
        )
        self.assertEqual(
            1, len(list_sites(conn, self._context("org-aaa"), include_archived=False))
        )
        self.assertEqual(
            1, len(list_assets(conn, self._context("org-aaa"), include_archived=False))
        )
        self.assertEqual(
            2, len(list_sites(conn, self._context("org-aaa"), include_archived=True))
        )
        self.assertEqual(
            2, len(list_assets(conn, self._context("org-aaa"), include_archived=True))
        )

    def test_t5_idempotent_archives_and_empty_site(self):
        conn = self._open_migrated()
        self._insert_organization(conn)
        site = create_site(
            conn, self._context("org-aaa"), code="main", name="Site A", clock=self._clock()
        )
        asset = create_asset(
            conn,
            self._context("org-aaa"),
            site_id=site["id"],
            tag="pump-001",
            name="Pump 001",
            criticality="medium",
            purchase_cost_cents=10000,
            clock=self._clock(),
        )
        empty_site = create_site(
            conn, self._context("org-aaa"), code="empty", name="Empty Site", clock=self._clock()
        )
        first = archive_asset(
            conn, self._context("org-aaa"), asset_id=asset["id"], clock=self._clock(13)
        )
        second = archive_asset(
            conn, self._context("org-aaa"), asset_id=asset["id"], clock=self._clock(14)
        )
        self.assertEqual(first["archived_at"], second["archived_at"])
        site_first = archive_site(
            conn, self._context("org-aaa"), site_id=site["id"], clock=self._clock(15)
        )
        site_second = archive_site(
            conn, self._context("org-aaa"), site_id=site["id"], clock=self._clock(16)
        )
        self.assertEqual(site_first["archived_at"], site_second["archived_at"])
        archived_empty = archive_site(
            conn, self._context("org-aaa"), site_id=empty_site["id"], clock=self._clock(17)
        )
        self.assertIsNotNone(archived_empty["archived_at"])

    def test_t6_unarchive_clears_timestamp(self):
        conn = self._open_migrated()
        self._insert_organization(conn)
        site = create_site(
            conn, self._context("org-aaa"), code="main", name="Site A", clock=self._clock()
        )
        asset = create_asset(
            conn,
            self._context("org-aaa"),
            site_id=site["id"],
            tag="pump-001",
            name="Pump 001",
            criticality="medium",
            purchase_cost_cents=10000,
            clock=self._clock(),
        )
        archive_asset(
            conn, self._context("org-aaa"), asset_id=asset["id"], clock=self._clock(13)
        )
        archive_site(
            conn, self._context("org-aaa"), site_id=site["id"], clock=self._clock(14)
        )
        unarchived_asset = unarchive_asset(
            conn, self._context("org-aaa"), asset_id=asset["id"], clock=self._clock(15)
        )
        self.assertIsNone(unarchived_asset["archived_at"])
        unarchived_site = unarchive_site(
            conn, self._context("org-aaa"), site_id=site["id"], clock=self._clock(16)
        )
        self.assertIsNone(unarchived_site["archived_at"])
        self.assertEqual(
            1, len(list_sites(conn, self._context("org-aaa"), include_archived=False))
        )
        self.assertEqual(
            1, len(list_assets(conn, self._context("org-aaa"), include_archived=False))
        )

    def test_t7_cross_organization_no_leak_scoping(self):
        conn = self._open_migrated()
        self._insert_organization(conn)
        site = create_site(
            conn, self._context("org-aaa"), code="main", name="Site A", clock=self._clock()
        )
        asset = create_asset(
            conn,
            self._context("org-aaa"),
            site_id=site["id"],
            tag="pump-001",
            name="Pump 001",
            criticality="medium",
            purchase_cost_cents=10000,
            clock=self._clock(),
        )
        cross_org_context = self._context("org-bbb")
        nonexistent_site_id = "does-not-exist"
        site_calls = (
            lambda: archive_site(
                conn, cross_org_context, site_id=nonexistent_site_id, clock=self._clock(13)
            ),
            lambda: archive_site(
                conn, cross_org_context, site_id=site["id"], clock=self._clock(13)
            ),
            lambda: unarchive_site(
                conn, cross_org_context, site_id=nonexistent_site_id, clock=self._clock(13)
            ),
            lambda: unarchive_site(
                conn, cross_org_context, site_id=site["id"], clock=self._clock(13)
            ),
        )
        for call in site_calls:
            with self.subTest(call=call), self.assertRaises(NotFoundError) as caught:
                call()
            self.assertEqual("site not found", caught.exception.args[0])
        asset_calls = (
            lambda: archive_asset(
                conn, cross_org_context, asset_id="no-such-asset", clock=self._clock(13)
            ),
            lambda: archive_asset(
                conn, cross_org_context, asset_id=asset["id"], clock=self._clock(13)
            ),
            lambda: unarchive_asset(
                conn, cross_org_context, asset_id="no-such-asset", clock=self._clock(13)
            ),
            lambda: unarchive_asset(
                conn, cross_org_context, asset_id=asset["id"], clock=self._clock(13)
            ),
        )
        for call in asset_calls:
            with self.subTest(call=call), self.assertRaises(NotFoundError):
                call()
