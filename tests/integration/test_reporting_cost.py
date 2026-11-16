"""Integration tests (T058): READ-ONLY per-asset cost report.

These tests apply the REAL shipped migrations to a temporary file database
and then exercise :func:`opsledger.reporting.cost_report.asset_cost_report`
against that migrated schema — no CREATE TABLE anywhere, mirroring the
migrate-a-temp-db setup style. Each behaviour and boundary is covered: the
``reporting.read`` permission gate before any query, the malformed
authorization context (a role outside KNOWN_ROLES, or a context without a
role), the recorded standard-cost consumption pricing (never purchase
prices), the machine-verified fixture totals, zero-filled inactive assets,
and organization scoping.
"""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from opsledger.assets import create_asset, create_site
from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect, transaction
from opsledger.core.errors import ValidationError
from opsledger.core.migrations import migrate
from opsledger.inventory import adjust_stock, consume_reservation, reserve_stock
from opsledger.parts import create_part, create_stock_location
from opsledger.purchasing.lifecycle import (
    approve_purchase_request,
    submit_purchase_request,
)
from opsledger.purchasing.orders import issue_order
from opsledger.purchasing.receipts import receive_order
from opsledger.purchasing.requests import create_purchase_request
from opsledger.purchasing.vendors import create_vendor
from opsledger.reporting.cost_report import asset_cost_report
from opsledger.workorders import create_work_order, record_labor


class _Actor:
    """Tiny authorization stub: the role attribute is the only read."""

    def __init__(self, role):
        self.role = role


class PerAssetCostReportTest(unittest.TestCase):
    """Integration tests for asset_cost_report() on the real migrated schema."""

    def setUp(self):
        self._clock_tick = 0

    def _open_migrated(self):
        """Create a temporary file database with the REAL shipped migrations."""
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
                    user_id + "@example.com",
                    "User " + user_id,
                    "2026-11-06T12:00:00Z",
                ),
            )

    def _seed_membership(self, conn, organization_id, user_id, role):
        with transaction(conn) as tx:
            tx.execute(
                "INSERT OR IGNORE INTO memberships (organization_id, user_id, role, created_at)"
                " VALUES (?, ?, ?, ?)",
                (organization_id, user_id, role, "2026-11-06T12:00:00Z"),
            )

    def _context(self, organization_id, actor_id=None):
        return OrganizationContext(organization_id=organization_id, actor_id=actor_id)

    def _tick_clock(self):
        """Every call hands back a fresh clock one second later."""
        self._clock_tick += 1
        return FixedClock(
            datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)
            + timedelta(seconds=self._clock_tick)
        )

    def _build_org_fixture(self, conn):
        """Assemble the machine-verified cost-report fixture for organization aaa."""
        self._seed_organization(conn, "org-aaa")
        self._seed_user(conn, "user-111")
        self._seed_user(conn, "user-222")
        self._seed_membership(conn, "org-aaa", "user-222", "approver")
        context = self._context("org-aaa", actor_id="user-111")

        site = create_site(
            conn, context, code="site-1", name="Main site", clock=self._tick_clock()
        )
        asset = create_asset(
            conn,
            context,
            site_id=site["id"],
            tag="pump-001",
            name="Coolant pump",
            criticality="high",
            purchase_cost_cents=10000,
            clock=self._tick_clock(),
        )
        inactive = create_asset(
            conn,
            context,
            site_id=site["id"],
            tag="pump-002",
            name="Standby pump",
            criticality="low",
            purchase_cost_cents=8000,
            clock=self._tick_clock(),
        )
        part = create_part(
            conn,
            context,
            sku="bolt-m8",
            name="M8 bolt",
            unit_of_measure="unit",
            standard_cost_cents=250,
            clock=self._tick_clock(),
        )
        store = create_stock_location(
            conn, context, code="sto-1", name="Main store", clock=self._tick_clock()
        )
        work_order = create_work_order(
            conn,
            context,
            site_id=site["id"],
            asset_id=asset["id"],
            number="WO-0001",
            title="Rebuild pump",
            description="Pump vibration",
            priority="high",
            requester_id="user-111",
            clock=self._tick_clock(),
        )

        adjust_stock(
            conn,
            context,
            part_id=part["id"],
            location_id=store["id"],
            quantity_delta=100,
            reason="opening intake",
            expected_version=1,
            actor_id="user-111",
            clock=self._tick_clock(),
        )
        reservation = reserve_stock(
            conn,
            context,
            part_id=part["id"],
            location_id=store["id"],
            work_order_id=work_order["id"],
            quantity=10,
            expected_version=2,
            actor_id="user-111",
            clock=self._tick_clock(),
        )
        consume_reservation(
            conn,
            context,
            reservation_id=reservation["id"],
            quantity=10,
            expected_version=3,
            actor_id="user-111",
            clock=self._tick_clock(),
        )
        record_labor(
            conn,
            context,
            work_order_id=work_order["id"],
            technician_id="user-111",
            minutes=90,
            rate_cents_per_hour=8000,
            clock=self._tick_clock(),
        )
        return context, asset, inactive, part, store, work_order

    def test_cost_report_requires_reporting_read_permission(self):
        conn = self._open_migrated()
        self._seed_organization(conn, "org-aaa")
        context = self._context("org-aaa")

        with self.assertRaises(ValidationError):
            asset_cost_report(conn, context, actor=_Actor(None))
        with self.assertRaises(ValidationError):
            asset_cost_report(conn, context, actor=_Actor("pilot"))
        for role in ("technician", "admin", "auditor"):
            self.assertEqual(
                [], asset_cost_report(conn, context, actor=_Actor(role))
            )

    def test_cost_report_uses_recorded_consumption_and_labor_cost(self):
        conn = self._open_migrated()
        context, asset, _inactive, _part, _store, _work_order = self._build_org_fixture(
            conn
        )

        rows = asset_cost_report(conn, context, actor=_Actor("technician"))

        self.assertEqual(2, len(rows))
        row = rows[0]
        self.assertEqual(asset["id"], row["asset_id"])
        self.assertEqual("pump-001", row["tag"])
        self.assertEqual(12000, row["labor_cost_cents"])
        self.assertEqual(2500, row["consumed_part_cost_cents"])
        self.assertEqual(14500, row["total_cost_cents"])

    def test_cost_report_excludes_purchase_prices(self):
        conn = self._open_migrated()
        context, asset, _inactive, part, store, _work_order = self._build_org_fixture(
            conn
        )

        before = asset_cost_report(conn, context, actor=_Actor("auditor"))

        vendor = create_vendor(
            conn, context, name="Acme", contact_email=None, clock=self._tick_clock()
        )
        request = create_purchase_request(
            conn,
            context,
            vendor_id=vendor["id"],
            lines=[{"part_id": part["id"], "quantity": 10, "unit_cost_cents": 300}],
            clock=self._tick_clock(),
        )
        submitted = submit_purchase_request(
            conn,
            context,
            purchase_request_id=request["id"],
            expected_version=1,
            clock=self._tick_clock(),
        )
        self.assertEqual("submitted", submitted["status"])
        approver = self._context("org-aaa", actor_id="user-222")
        approved = approve_purchase_request(
            conn,
            approver,
            purchase_request_id=request["id"],
            expected_version=2,
            clock=self._tick_clock(),
            reason="repair parts",
        )
        self.assertEqual("approved", approved["status"])
        order, _issue_record, order_replayed = issue_order(
            conn,
            context,
            purchase_request_id=request["id"],
            expected_version=3,
            actor_id="user-111",
            clock=self._tick_clock(),
            idempotency_key="issue-cost-report",
        )
        self.assertFalse(order_replayed)
        self.assertEqual("open", order["status"])
        receipt, _receipt_record, receipt_replayed = receive_order(
            conn,
            context,
            purchase_order_id=order["id"],
            stock_location_id=store["id"],
            lines=[{"part_id": part["id"], "quantity": 6}],
            expected_version=order["version"],
            actor_id="user-111",
            clock=self._tick_clock(),
            idempotency_key="receipt-cost-report",
        )
        self.assertFalse(receipt_replayed)
        self.assertEqual("received", receipt["status"])

        after = asset_cost_report(conn, context, actor=_Actor("auditor"))

        self.assertEqual(before, after)
        row = next(item for item in after if item["asset_id"] == asset["id"])
        self.assertEqual(12000, row["labor_cost_cents"])
        self.assertEqual(2500, row["consumed_part_cost_cents"])
        self.assertEqual(14500, row["total_cost_cents"])

    def test_cost_report_zero_fills_inactive_assets(self):
        conn = self._open_migrated()
        context, asset, inactive, _part, _store, _work_order = self._build_org_fixture(
            conn
        )

        rows = asset_cost_report(conn, context, actor=_Actor("technician"))

        self.assertEqual([asset["id"], inactive["id"]], [row["asset_id"] for row in rows])
        inactive_row = rows[1]
        self.assertEqual(0, inactive_row["labor_cost_cents"])
        self.assertEqual(0, inactive_row["consumed_part_cost_cents"])
        self.assertEqual(0, inactive_row["total_cost_cents"])

    def test_cost_report_is_org_scoped(self):
        conn = self._open_migrated()
        context, asset, inactive, _part, _store, _work_order = self._build_org_fixture(
            conn
        )

        self._seed_organization(conn, "org-bbb")
        other = self._context("org-bbb", actor_id="user-222")
        other_site = create_site(
            conn, other, code="site-2", name="Branch site", clock=self._tick_clock()
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
        other_work_order = create_work_order(
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
        record_labor(
            conn,
            other,
            work_order_id=other_work_order["id"],
            technician_id="user-222",
            minutes=30,
            rate_cents_per_hour=9000,
            clock=self._tick_clock(),
        )

        own = asset_cost_report(conn, context, actor=_Actor("technician"))

        self.assertNotIn(other_asset["id"], [row["asset_id"] for row in own])
        self.assertEqual([asset["id"], inactive["id"]], [row["asset_id"] for row in own])

        reverse = asset_cost_report(conn, other, actor=_Actor("technician"))

        self.assertEqual([other_asset["id"]], [row["asset_id"] for row in reverse])
        other_row = reverse[0]
        self.assertEqual(4500, other_row["labor_cost_cents"])


if __name__ == "__main__":
    unittest.main()
