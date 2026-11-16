"""Integration tests (T059): READ-ONLY cross-module search.

These tests apply the REAL shipped migrations to a temporary file database
and then exercise :func:`opsledger.reporting.search.search` against that
migrated schema — no CREATE TABLE anywhere, following the
migrate-a-temp-db setup convention. Every behaviour and boundary is
covered: the ``reporting.read`` permission gate before any query, the
malformed authorization context (a context without a known role), query
validation (empty, whitespace-only, non-string), cross-module substring
matching with machine-verified counts, case-insensitivity, literal LIKE
wildcards, organization scoping without cross-organization leaks, and the
20-match cap per entity kind.
"""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from opsledger.assets import create_asset, create_site
from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect, transaction
from opsledger.core.migrations import migrate
from opsledger.core.errors import ValidationError
from opsledger.parts import create_part
from opsledger.reporting.search import search
from opsledger.workorders import create_work_order


class _Actor:
    """Minimal authorization context stub: role attribute only."""

    def __init__(self, role):
        self.role = role


class SearchTests(unittest.TestCase):
    """Integration tests for search() on the real migrated schema."""

    def setUp(self):
        self._clock_step = 0

    def _open_migrated(self):
        """Open a temporary file database with the REAL shipped migrations."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda: connect(tmp.name).close())
        conn = connect(tmp.name)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def _seed_organization(self, conn, organization_id):
        with transaction(conn) as tx:
            tx.execute(
                "INSERT OR IGNORE INTO organizations (id, slug, name, created_at)"
                " VALUES (?, ?, ?, ?)",
                (
                    organization_id,
                    organization_id,
                    "Organization " + organization_id,
                    "2026-11-06T12:00:00Z",
                ),
            )

    def _seed_user(self, conn, user_id):
        with transaction(conn) as tx:
            tx.execute(
                "INSERT OR IGNORE INTO users (id, email, display_name, created_at)"
                " VALUES (?, ?, ?, ?)",
                (
                    user_id,
                    user_id + "@example.test",
                    "User " + user_id,
                    "2026-11-06T12:00:00Z",
                ),
            )

    def _context(self, organization_id):
        return OrganizationContext(organization_id=organization_id)

    def _tick_clock(self):
        """Each call returns a NEW clock one second later."""
        self._clock_step += 1
        return FixedClock(
            datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)
            + timedelta(seconds=self._clock_step)
        )

    def _build_org_aaa_fixture(self, conn):
        """Build the machine-verified fixture for organization aaa."""
        self._seed_organization(conn, "org-aaa")
        self._seed_user(conn, "user-111")
        context = self._context("org-aaa")

        site_alpha = create_site(
            conn, context, code="site-alpha", name="Site alpha", clock=self._tick_clock()
        )
        site_beta = create_site(
            conn, context, code="site-beta", name="Site beta", clock=self._tick_clock()
        )

        pump_one = create_asset(
            conn,
            context,
            site_id=site_alpha["id"],
            tag="pump-001",
            name="Pump 001",
            criticality="high",
            purchase_cost_cents=10000,
            clock=self._tick_clock(),
        )
        create_asset(
            conn,
            context,
            site_id=site_alpha["id"],
            tag="pump-002",
            name="Pump 002",
            criticality="low",
            purchase_cost_cents=20000,
            clock=self._tick_clock(),
        )
        press_one = create_asset(
            conn,
            context,
            site_id=site_beta["id"],
            tag="press-001",
            name="Press 001",
            criticality="low",
            purchase_cost_cents=30000,
            clock=self._tick_clock(),
        )

        create_work_order(
            conn,
            context,
            site_id=site_alpha["id"],
            asset_id=pump_one["id"],
            number="WO-0001",
            title="Fix pump one",
            description="Pump one stopped unexpectedly",
            priority="high",
            requester_id="user-111",
            clock=self._tick_clock(),
        )
        create_work_order(
            conn,
            context,
            site_id=site_beta["id"],
            asset_id=press_one["id"],
            number="WO-0002",
            title="Service press",
            description="Routine press service",
            priority="medium",
            requester_id="user-111",
            clock=self._tick_clock(),
        )

        create_part(
            conn,
            context,
            sku="bolt-m8",
            name="Bolt M8",
            unit_of_measure="unit",
            standard_cost_cents=250,
            clock=self._tick_clock(),
        )
        return context

    def test_search_requires_reporting_read_permission(self):
        conn = self._open_migrated()
        self._seed_organization(conn, "org-aaa")
        context = self._context("org-aaa")

        with self.assertRaises(ValidationError):
            search(conn, context, actor=_Actor(None), query="pump")
        with self.assertRaises(ValidationError):
            search(conn, context, actor=_Actor("pilot"), query="pump")

        for role in ("technician", "admin", "auditor"):
            result = search(conn, context, actor=_Actor(role), query="pump")
            self.assertIsInstance(result, dict)
            self.assertEqual([], result["assets"])
            self.assertEqual([], result["work_orders"])
            self.assertEqual([], result["parts"])

    def test_search_query_validation(self):
        conn = self._open_migrated()
        self._seed_organization(conn, "org-aaa")
        context = self._context("org-aaa")

        for bad_query in ("", "   ", 42):
            with self.assertRaises(ValidationError):
                search(conn, context, actor=_Actor("technician"), query=bad_query)

    def test_search_matches_across_modules_with_machine_verified_counts(self):
        conn = self._open_migrated()
        context = self._build_org_aaa_fixture(conn)

        result = search(conn, context, actor=_Actor("technician"), query="pump")

        self.assertEqual("pump", result["query"])
        self.assertEqual(2, len(result["assets"]))
        self.assertEqual(
            ["pump-001", "pump-002"],
            [entry["tag"] for entry in result["assets"]],
        )
        self.assertEqual(1, len(result["work_orders"]))
        self.assertEqual("WO-0001", result["work_orders"][0]["number"])
        self.assertEqual([], result["parts"])

    def test_search_is_case_insensitive(self):
        conn = self._open_migrated()
        context = self._build_org_aaa_fixture(conn)

        lowercase = search(conn, context, actor=_Actor("technician"), query="pump")
        uppercase = search(conn, context, actor=_Actor("technician"), query="PUMP")

        self.assertEqual(2, len(uppercase["assets"]))
        self.assertEqual(
            [entry["tag"] for entry in lowercase["assets"]],
            [entry["tag"] for entry in uppercase["assets"]],
        )

        bolt_lower = search(conn, context, actor=_Actor("technician"), query="bolt")
        bolt_upper = search(conn, context, actor=_Actor("technician"), query="BOLT")

        self.assertEqual(1, len(bolt_lower["parts"]))
        self.assertEqual(1, len(bolt_upper["parts"]))

    def test_search_escapes_like_wildcards(self):
        conn = self._open_migrated()
        context = self._build_org_aaa_fixture(conn)

        for pattern in ("%", "pump%", "_"):
            result = search(conn, context, actor=_Actor("technician"), query=pattern)

            self.assertEqual([], result["assets"])
            self.assertEqual([], result["work_orders"])
            self.assertEqual([], result["parts"])

    def test_search_is_org_scoped_no_leak(self):
        conn = self._open_migrated()
        context = self._build_org_aaa_fixture(conn)
        aaa_asset_ids = [
            entry["id"]
            for entry in conn.execute(
                "SELECT id FROM assets WHERE organization_id = 'org-aaa'"
            ).fetchall()
        ]
        self.assertEqual(3, len(aaa_asset_ids))

        self._seed_organization(conn, "org-bbb")
        other = self._context("org-bbb")
        other_site = create_site(
            conn, other, code="site-alpha", name="Other site alpha", clock=self._tick_clock()
        )
        other_asset = create_asset(
            conn,
            other,
            site_id=other_site["id"],
            tag="pump-001",
            name="Other pump 001",
            criticality="low",
            purchase_cost_cents=1000,
            clock=self._tick_clock(),
        )

        forward = search(conn, context, actor=_Actor("technician"), query="pump")

        forward_asset_ids = [entry["id"] for entry in forward["assets"]]
        self.assertNotIn(other_asset["id"], forward_asset_ids)
        for work_order in forward["work_orders"]:
            self.assertNotEqual(other_asset["id"], work_order["id"])
            self.assertNotEqual(other_site["id"], work_order["id"])

        reverse = search(conn, other, actor=_Actor("technician"), query="pump")

        self.assertEqual(1, len(reverse["assets"]))
        self.assertEqual([], reverse["work_orders"])
        self.assertEqual(other_asset["id"], reverse["assets"][0]["id"])
        self.assertEqual("pump-001", reverse["assets"][0]["tag"])
        self.assertNotIn(reverse["assets"][0]["id"], aaa_asset_ids)

    def test_search_caps_results_at_twenty(self):
        conn = self._open_migrated()
        self._seed_organization(conn, "org-aaa")
        context = self._context("org-aaa")
        site = create_site(
            conn, context, code="main", name="Main site", clock=self._tick_clock()
        )
        for index in range(1, 26):
            create_asset(
                conn,
                context,
                site_id=site["id"],
                tag=f"asset-{index:03d}",
                name=f"Searchable asset {index:03d}",
                criticality="low",
                purchase_cost_cents=100,
                clock=self._tick_clock(),
            )

        result = search(conn, context, actor=_Actor("technician"), query="searchable")

        self.assertEqual(20, len(result["assets"]))
        self.assertEqual(
            [f"asset-{index:03d}" for index in range(1, 21)],
            [entry["tag"] for entry in result["assets"]],
        )


if __name__ == "__main__":
    unittest.main()
