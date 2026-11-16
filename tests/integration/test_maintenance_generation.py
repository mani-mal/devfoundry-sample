"""Integration tests (T051): idempotent generation of maintenance work orders.

REAL shipped migrations on a temporary file database (no CREATE TABLE),
driven through the public functions only; each _tick_clock call returns
a FRESH DISTINCT clock instant (UTC, RFC3339 Z, second precision).
"""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from opsledger.assets import create_asset, create_site
from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect
from opsledger.core.migrations import migrate
from opsledger.maintenance.generate import generate_due_work_orders
from opsledger.maintenance.plans import create_maintenance_plan, archive_maintenance_plan

RUN_CLOCK = FixedClock(datetime(2026, 2, 15, tzinfo=timezone.utc))


class MaintenanceGenerationTest(unittest.TestCase):
    def setUp(self):
        self._clock_tick = 0

    def _open_migrated(self):
        """Open a temporary file database with the REAL shipped migrations (no CREATE TABLE)."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda: connect(tmp.name).close())
        conn = connect(tmp.name)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def _seed_rows(self, conn, organization_id="org-aaa"):
        """Seed the organization and users with parameterized SQL INSERTs."""
        created_text = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with conn:
            conn.execute("INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)", (organization_id, organization_id, "Organization", created_text))
            conn.execute("INSERT INTO users (id, email, display_name, created_at) VALUES (?, ?, ?, ?)", ("user-111", "user-111@example.com", "Requester One", created_text))
            conn.execute("INSERT INTO users (id, email, display_name, created_at) VALUES (?, ?, ?, ?)", ("user-999", "user-999@example.com", "Second User", created_text))

    def _context(self, organization_id="org-aaa", actor_id="user-111"):
        return OrganizationContext(organization_id=organization_id, actor_id=actor_id)

    def _tick_clock(self):
        """Each call returns a FRESH DISTINCT clock: UTC, RFC3339 Z, seconds."""
        self._clock_tick += 1
        return FixedClock(datetime.now(timezone.utc) + timedelta(seconds=self._clock_tick))

    def _seed_plan(self, conn, context):
        """Create one owned site, asset, and active maintenance plan through the public services."""
        site = create_site(conn, context, code="site-1", name="Site", clock=self._tick_clock())
        asset = create_asset(conn, context, site_id=site["id"], tag="tag-1", name="Asset", criticality="low", purchase_cost_cents=1000, clock=self._tick_clock())
        return create_maintenance_plan(
            conn,
            context,
            site_id=site["id"],
            asset_id=asset["id"],
            name="Plan",
            description="Desc",
            interval_days=30,
            horizon_days=60,
            clock=FixedClock(datetime(2026, 1, 1, tzinfo=timezone.utc)),
        )

    def test_t1_generate_creates_one_order_per_due_date(self):
        conn = self._open_migrated()
        self._seed_rows(conn)
        context = self._context()
        plan = self._seed_plan(conn, context)
        created = generate_due_work_orders(
            conn,
            context,
            actor_id=context.actor_id,
            clock=RUN_CLOCK,
            horizon_days=60,
        )
        self.assertEqual(2, len(created))
        self.assertEqual(["2026-01-01", "2026-01-31"], [item["scheduled_date"] for item in created])
        for item in created:
            self.assertEqual({"run_id", "work_order_id", "scheduled_date"}, set(item))
        self.assertEqual(
            ["M-" + plan["id"] + "-2026-01-01", "M-" + plan["id"] + "-2026-01-31"],
            [row["number"] for row in conn.execute("SELECT * FROM work_orders").fetchall()],
        )
        self.assertEqual(
            ["Maintenance: Plan", "Maintenance: Plan"],
            [row["title"] for row in conn.execute("SELECT * FROM work_orders").fetchall()],
        )
        self.assertEqual(
            ["generated", "generated"],
            [row["status"] for row in conn.execute("SELECT * FROM maintenance_runs").fetchall()],
        )
        self.assertEqual(
            [1, 1],
            [row["attempt_count"] for row in conn.execute("SELECT * FROM maintenance_runs").fetchall()],
        )

    def test_t2_second_generate_call_is_idempotent(self):
        conn = self._open_migrated()
        self._seed_rows(conn)
        context = self._context()
        self._seed_plan(conn, context)
        first = generate_due_work_orders(conn, context, actor_id=context.actor_id, clock=RUN_CLOCK)
        self.assertEqual(2, len(first))
        second = generate_due_work_orders(conn, context, actor_id=context.actor_id, clock=RUN_CLOCK)
        self.assertEqual([], second)
        self.assertEqual(2, conn.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0])

    def test_t3_archived_plan_generates_nothing(self):
        conn = self._open_migrated()
        self._seed_rows(conn)
        context = self._context()
        plan = self._seed_plan(conn, context)
        archive_maintenance_plan(conn, context, plan_id=plan["id"], expected_version=plan["version"], clock=self._tick_clock())
        created = generate_due_work_orders(conn, context, actor_id=context.actor_id, clock=RUN_CLOCK)
        self.assertEqual([], created)
        self.assertEqual(0, conn.execute("SELECT COUNT(*) FROM maintenance_runs").fetchone()[0])
        self.assertEqual(0, conn.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0])
