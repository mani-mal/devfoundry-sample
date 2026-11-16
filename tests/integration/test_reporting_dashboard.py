"""Integration tests (T057): READ-ONLY dashboard aggregation.

These tests apply the REAL shipped migrations to a temporary file database
and then exercise :func:`opsledger.reporting.dashboard.dashboard` against
that migrated schema — no CREATE TABLE anywhere, mirroring the
migrate-a-temp-db setup style. Each behaviour and boundary is covered: the
``reporting.read`` permission gate before any query, the malformed
authorization context (a context without a known role), the dict shape with
all seven statuses zero-filled, the machine-verified fixture totals, and
organization scoping.
"""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from opsledger.assets import create_asset, create_site
from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect, transaction
from opsledger.core.errors import PermissionDeniedError, ValidationError
from opsledger.core.migrations import migrate
from opsledger.identity.permissions import BASE_PERMISSIONS
from opsledger.inventory import (
    adjust_stock,
    consume_reservation,
    release_reservation,
    reserve_stock,
)
from opsledger.parts import create_part, create_stock_location
from opsledger.reporting.dashboard import dashboard
from opsledger.workorders import create_work_order, record_labor
from opsledger.workorders.transitions import transition_work_order


class _Actor:
    """Tiny authorization context stub: role attribute only."""

    def __init__(self, role):
        self.role = role


class DashboardAggregationTests(unittest.TestCase):
    """Integration tests for dashboard() on the real migrated schema."""

    def setUp(self):
        self._clock_tick = 0

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

    def _context(self, organization_id):
        return OrganizationContext(organization_id=organization_id)

    def _tick_clock(self):
        """Each call returns a NEW clock one second later."""
        self._clock_tick += 1
        return FixedClock(
            datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)
            + timedelta(seconds=self._clock_tick)
        )

    def _build_org_aaa_fixture(self, conn):
        """Build the machine-verified fixture for organization aaa."""
        self._seed_organization(conn, "org-aaa")
        context = self._context("org-aaa")

        site = create_site(
            conn, context, code="main", name="Main site", clock=self._tick_clock()
        )
        asset = create_asset(
            conn,
            context,
            site_id=site["id"],
            tag="pump-1",
            name="Coolant pump",
            criticality="high",
            purchase_cost_cents=10000,
            clock=self._tick_clock(),
        )
        part = create_part(
            conn,
            context,
            sku="bolt-m8",
            name="M8 bolt",
            unit_of_measure="unit",
            standard_cost_cents=2500,
            clock=self._tick_clock(),
        )
        first_store = create_stock_location(
            conn, context, code="sto-1", name="Main store", clock=self._tick_clock()
        )
        second_store = create_stock_location(
            conn, context, code="sto-2", name="Overflow store", clock=self._tick_clock()
        )

        first_work_order = create_work_order(
            conn,
            context,
            site_id=site["id"],
            asset_id=asset["id"],
            number="WO-0001",
            title="Inspect pump",
            description="Routine inspection",
            priority="medium",
            requester_id="user-111",
            clock=self._tick_clock(),
        )
        second_work_order = create_work_order(
            conn,
            context,
            site_id=site["id"],
            asset_id=asset["id"],
            number="WO-0002",
            title="Rebuild pump",
            description="Pump vibration",
            priority="high",
            requester_id="user-111",
            clock=self._tick_clock(),
        )
        self.assertEqual(
            "assigned",
            transition_work_order(
                conn,
                context,
                work_order_id=second_work_order["id"],
                to_status="assigned",
                expected_version=1,
                reason="assign technician",
                actor_id="user-111",
                clock=self._tick_clock(),
            )["status"],
        )
        self.assertEqual(
            "in_progress",
            transition_work_order(
                conn,
                context,
                work_order_id=second_work_order["id"],
                to_status="in_progress",
                expected_version=2,
                reason="start work",
                actor_id="user-111",
                clock=self._tick_clock(),
            )["status"],
        )
        third_work_order = create_work_order(
            conn,
            context,
            site_id=site["id"],
            asset_id=asset["id"],
            number="WO-0003",
            title="Replace pump seals",
            description="Pump seals are leaking",
            priority="high",
            requester_id="user-111",
            clock=self._tick_clock(),
        )
        self.assertEqual(
            "assigned",
            transition_work_order(
                conn,
                context,
                work_order_id=third_work_order["id"],
                to_status="assigned",
                expected_version=1,
                reason="assign technician",
                actor_id="user-111",
                clock=self._tick_clock(),
            )["status"],
        )
        self.assertEqual(
            "in_progress",
            transition_work_order(
                conn,
                context,
                work_order_id=third_work_order["id"],
                to_status="in_progress",
                expected_version=2,
                reason="start work",
                actor_id="user-111",
                clock=self._tick_clock(),
            )["status"],
        )
        self.assertEqual(
            "completed",
            transition_work_order(
                conn,
                context,
                work_order_id=third_work_order["id"],
                to_status="completed",
                expected_version=3,
                reason="work finished",
                actor_id="user-111",
                clock=self._tick_clock(),
            )["status"],
        )

        adjust_stock(
            conn,
            context,
            part_id=part["id"],
            location_id=first_store["id"],
            quantity_delta=100,
            reason="opening",
            expected_version=1,
            actor_id="user-111",
            clock=self._tick_clock(),
        )
        adjust_stock(
            conn,
            context,
            part_id=part["id"],
            location_id=second_store["id"],
            quantity_delta=40,
            reason="overflow intake",
            expected_version=1,
            actor_id="user-111",
            clock=self._tick_clock(),
        )
        first_reservation = reserve_stock(
            conn,
            context,
            part_id=part["id"],
            location_id=first_store["id"],
            work_order_id=first_work_order["id"],
            quantity=15,
            expected_version=2,
            actor_id="user-111",
            clock=self._tick_clock(),
        )
        consume_reservation(
            conn,
            context,
            reservation_id=first_reservation["id"],
            quantity=10,
            expected_version=3,
            actor_id="user-111",
            clock=self._tick_clock(),
        )
        second_reservation = reserve_stock(
            conn,
            context,
            part_id=part["id"],
            location_id=first_store["id"],
            work_order_id=first_work_order["id"],
            quantity=5,
            expected_version=4,
            actor_id="user-111",
            clock=self._tick_clock(),
        )
        release_reservation(
            conn,
            context,
            reservation_id=second_reservation["id"],
            quantity=5,
            expected_version=5,
            actor_id="user-111",
            clock=self._tick_clock(),
        )

        record_labor(
            conn,
            context,
            work_order_id=first_work_order["id"],
            technician_id="user-111",
            minutes=90,
            rate_cents_per_hour=8000,
            clock=self._tick_clock(),
        )
        record_labor(
            conn,
            context,
            work_order_id=first_work_order["id"],
            technician_id="user-111",
            minutes=100,
            rate_cents_per_hour=8000,
            clock=self._tick_clock(),
        )
        record_labor(
            conn,
            context,
            work_order_id=second_work_order["id"],
            technician_id="user-111",
            minutes=60,
            rate_cents_per_hour=9000,
            clock=self._tick_clock(),
        )
        return context

    def test_dashboard_requires_reporting_read_permission(self):
        conn = self._open_migrated()
        self._seed_organization(conn, "org-aaa")
        context = self._context("org-aaa")

        with self.assertRaises(ValidationError):
            dashboard(conn, context, actor=_Actor(None))
        with self.assertRaises(ValidationError):
            dashboard(conn, context, actor=_Actor("pilot"))
        with patch.dict(
            BASE_PERMISSIONS, {"supervisor": frozenset({"org.manage_members"})}
        ):
            with self.assertRaises(PermissionDeniedError):
                dashboard(conn, context, actor=_Actor("supervisor"))
        for role in ("technician", "admin", "auditor"):
            result = dashboard(conn, context, actor=_Actor(role))
            self.assertIsInstance(result, dict)

        absent = self._context("org-absent")
        with self.assertRaises(ValidationError):
            dashboard(conn, absent, actor=_Actor(None))

    def test_dashboard_counts_from_independent_fixture(self):
        conn = self._open_migrated()
        context = self._build_org_aaa_fixture(conn)

        result = dashboard(conn, context, actor=_Actor("auditor"))

        self.assertEqual(3, result["work_orders"]["total"])
        self.assertEqual(
            {
                "open": 1,
                "assigned": 0,
                "in_progress": 1,
                "blocked": 0,
                "completed": 1,
                "closed": 0,
                "cancelled": 0,
            },
            result["work_orders"]["by_status"],
        )
        self.assertEqual(1, result["assets"]["total"])
        self.assertEqual(130, result["stock"]["on_hand"])
        self.assertEqual(5, result["stock"]["reserved"])
        self.assertEqual(34333, result["labor_cost_cents"])

    def test_dashboard_is_org_scoped(self):
        conn = self._open_migrated()
        self._build_org_aaa_fixture(conn)

        self._seed_organization(conn, "org-bbb")
        other = self._context("org-bbb")
        other_site = create_site(
            conn, other, code="main", name="Site B", clock=self._tick_clock()
        )
        other_asset = create_asset(
            conn,
            other,
            site_id=other_site["id"],
            tag="pump-b",
            name="Backup pump",
            criticality="low",
            purchase_cost_cents=5000,
            clock=self._tick_clock(),
        )
        create_work_order(
            conn,
            other,
            site_id=other_site["id"],
            asset_id=other_asset["id"],
            number="WO-9001",
            title="Swap pumps",
            description="Cut over to the backup pump",
            priority="low",
            requester_id="user-222",
            clock=self._tick_clock(),
        )

        own = dashboard(conn, self._context("org-aaa"), actor=_Actor("technician"))
        self.assertEqual(3, own["work_orders"]["total"])
        self.assertEqual(
            {
                "open": 1,
                "assigned": 0,
                "in_progress": 1,
                "blocked": 0,
                "completed": 1,
                "closed": 0,
                "cancelled": 0,
            },
            own["work_orders"]["by_status"],
        )
        self.assertEqual(130, own["stock"]["on_hand"])

        reverse = dashboard(conn, other, actor=_Actor("technician"))
        self.assertEqual(1, reverse["work_orders"]["total"])
        self.assertEqual(1, reverse["assets"]["total"])
        self.assertEqual(0, reverse["stock"]["on_hand"])
        self.assertEqual(0, reverse["stock"]["reserved"])

    def test_dashboard_zero_fills_every_status(self):
        conn = self._open_migrated()
        self._seed_organization(conn, "org-empty")

        result = dashboard(conn, self._context("org-empty"), actor=_Actor("technician"))

        self.assertEqual(0, result["work_orders"]["total"])
        self.assertEqual(
            ["open", "assigned", "in_progress", "blocked", "completed", "closed", "cancelled"],
            list(result["work_orders"]["by_status"]),
        )
        self.assertEqual([0] * 7, list(result["work_orders"]["by_status"].values()))
        self.assertEqual(0, result["assets"]["total"])
        self.assertEqual({"on_hand": 0, "reserved": 0}, result["stock"])
        self.assertEqual(0, result["labor_cost_cents"])


if __name__ == "__main__":
    unittest.main()
