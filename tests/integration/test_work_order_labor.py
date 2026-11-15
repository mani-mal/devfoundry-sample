"""Integration tests (T029b): work-order labor service.

These tests apply the REAL shipped migrations to a temporary file database
and then exercise :mod:`opsledger.workorders.labor` against that migrated
schema — no CREATE TABLE anywhere in the test. Acceptance (spec M4/T029):
negative minutes refused; the cost is computed server-side with integer
round-half-up; totals aggregate recorded entry costs; money is integer
cents throughout.
"""

import tempfile
import unittest
from datetime import datetime, timezone

from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError
from opsledger.core.migrations import migrate
from opsledger.assets import create_asset, create_site
from opsledger.workorders import create_work_order
from opsledger.workorders.labor import (
    MINUTES_MESSAGE,
    RATE_MESSAGE,
    labor_cost_cents,
    labor_total_cents,
    list_labor_entries,
    record_labor,
)


class LaborTests(unittest.TestCase):
    """Integration tests for the labor service on the real migrated schema."""

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

    def _context(self, organization_id="org-aaa"):
        return OrganizationContext(organization_id=organization_id)

    def _clock(self, hour=12):
        return FixedClock(datetime(2026, 11, 13, hour, 0, 0, tzinfo=timezone.utc))

    def _seed_work_order(self, conn, number="wo-100"):
        clock = self._clock()
        self._seed_organizations(conn)
        site_a = create_site(conn, self._context(), code="main", name="Site A", clock=clock)
        site_b = create_site(conn, self._context("org-bbb"), code="main", name="Site B", clock=clock)
        asset_a = create_asset(
            conn, self._context(), site_id=site_a["id"], tag="pump-001",
            name="Asset pump-001", criticality="medium", purchase_cost_cents=10000, clock=clock,
        )
        work_order = create_work_order(
            conn, self._context(), site_id=site_a["id"], asset_id=asset_a["id"],
            number=number, title="Rebuild pump", description="Full rebuild",
            priority="high", requester_id="user-111", clock=clock,
        )
        return site_a, site_b, work_order

    def _record(self, conn, work_order, minutes, rate, hour=15, note=None):
        return record_labor(
            conn, self._context(), work_order_id=work_order["id"], technician_id="user-111",
            minutes=minutes, rate_cents_per_hour=rate,
            clock=FixedClock(datetime(2026, 11, 13, hour, 0, 0, tzinfo=timezone.utc)), note=note,
        )

    def test_t1_labor_cost_cents_fixture_exact(self):
        self.assertEqual(12000, labor_cost_cents(90, 8000))
        self.assertEqual(13333, labor_cost_cents(100, 8000))
        self.assertEqual(6000, labor_cost_cents(45, 8000))

    def test_t2_negative_and_zero_minutes_refused(self):
        with self.assertRaises(ValidationError) as caught:
            labor_cost_cents(-30, 8000)
        self.assertEqual(MINUTES_MESSAGE, str(caught.exception))
        with self.assertRaises(ValidationError):
            labor_cost_cents(0, 8000)

    def test_t3_bool_and_non_int_minutes_refused(self):
        with self.assertRaises(ValidationError):
            labor_cost_cents(True, 8000)
        with self.assertRaises(ValidationError):
            labor_cost_cents(90.0, 8000)

    def test_t4_non_positive_rate_refused(self):
        with self.assertRaises(ValidationError) as caught:
            labor_cost_cents(90, 0)
        self.assertEqual(RATE_MESSAGE, str(caught.exception))
        with self.assertRaises(ValidationError):
            labor_cost_cents(90, -8000)

    def test_t5_record_labor_stores_server_side_cost(self):
        conn = self._open_migrated()
        _, _, work_order = self._seed_work_order(conn)
        entry = self._record(conn, work_order, 90, 8000, note="removal")
        self.assertEqual("lbr-", entry["id"][:4])
        self.assertEqual(12000, entry["cost_cents"])
        self.assertEqual(90, entry["minutes"])
        self.assertEqual("removal", entry["note"])

    def test_t6_total_aggregates_recorded_costs(self):
        conn = self._open_migrated()
        _, _, work_order = self._seed_work_order(conn)
        self._record(conn, work_order, 90, 8000, hour=15)
        self._record(conn, work_order, 100, 8000, hour=16)
        total = labor_total_cents(conn, self._context(), work_order_id=work_order["id"])
        self.assertEqual(25333, total)
