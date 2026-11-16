"""Regression suite (T056): time-boundary and interruption recovery.

Documented recovery: a work-order write that fails (or a simulated worker
crash) leaves the maintenance run 'pending' with attempt_count incremented
and last_error set. Rerunning generate_due_work_orders or
process_pending_runs completes the run idempotently: no duplicate work
order can be created because the (organization, plan, scheduled_date)
UNIQUE key on maintenance_runs and the duplicate-number ConflictError both
guard it, and a duplicate found on retry marks the run 'generated' instead
of raising. Time boundaries (month, year, leap day) are produced by
datetime.date arithmetic alone: every test pins its own FixedClock instant,
and this suite never reads the wall clock.
"""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from opsledger.assets import create_asset, create_site
from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect
from opsledger.core.migrations import migrate
from opsledger.maintenance.outbox import process_pending_runs
from opsledger.maintenance.generate import generate_due_work_orders
from opsledger.maintenance.plans import create_maintenance_plan

ORG_CLOCK = datetime(2024, 2, 28, tzinfo=timezone.utc)


class MaintenanceRegressionTest(unittest.TestCase):
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
        created_text = ORG_CLOCK.strftime("%Y-%m-%dT%H:%M:%SZ")
        with conn:
            conn.execute("INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)", (organization_id, organization_id, "Organization", created_text))
            conn.execute("INSERT INTO users (id, email, display_name, created_at) VALUES (?, ?, ?, ?)", ("user-111", "user-111@example.com", "Requester One", created_text))
            conn.execute("INSERT INTO users (id, email, display_name, created_at) VALUES (?, ?, ?, ?)", ("user-999", "user-999@example.com", "Second User", created_text))

    def _context(self, organization_id="org-aaa", actor_id="user-111"):
        return OrganizationContext(organization_id=organization_id, actor_id=actor_id)

    def _seed_plan(self, conn, context, *, interval_days, horizon_days, created_at):
        """Create one owned site, asset, and active plan through the public services."""
        site = create_site(conn, context, code="site-1", name="Site", clock=FixedClock(ORG_CLOCK))
        asset = create_asset(conn, context, site_id=site["id"], tag="tag-1", name="Asset", criticality="low", purchase_cost_cents=1000, clock=FixedClock(ORG_CLOCK))
        return create_maintenance_plan(
            conn,
            context,
            site_id=site["id"],
            asset_id=asset["id"],
            name="Plan",
            description="Desc",
            interval_days=interval_days,
            horizon_days=horizon_days,
            clock=FixedClock(created_at),
        )

    def _tick_clock(self, seconds):
        """Pinned instant for a test: timezone-aware UTC, no wall-clock reads."""
        return FixedClock(ORG_CLOCK + timedelta(seconds=seconds))

    def test_t1_leap_day_generation_is_deterministic(self):
        conn = self._open_migrated()
        self._seed_rows(conn)
        context = self._context()
        plan = self._seed_plan(
            conn,
            context,
            interval_days=365,
            horizon_days=366,
            created_at=datetime(2024, 3, 1, tzinfo=timezone.utc),
        )
        generated = generate_due_work_orders(
            conn,
            context,
            actor_id=context.actor_id,
            clock=FixedClock(datetime(2028, 2, 29, tzinfo=timezone.utc)),
        )
        self.assertEqual(5, len(generated))
        scheduled = [item["scheduled_date"] for item in generated]
        self.assertIn("2028-02-29", scheduled)
        self.assertEqual(
            ["2024-03-01", "2025-03-01", "2026-03-01", "2027-03-01", "2028-02-29"],
            sorted(scheduled),
        )
        repeated = generate_due_work_orders(
            conn,
            context,
            actor_id=context.actor_id,
            clock=FixedClock(datetime(2028, 2, 29, tzinfo=timezone.utc)),
        )
        self.assertEqual([], repeated)
        self.assertEqual(5, conn.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0])

    def test_t2_year_boundary_generation_exactly_two_runs(self):
        conn = self._open_migrated()
        self._seed_rows(conn)
        context = self._context()
        plan = self._seed_plan(
            conn,
            context,
            interval_days=10,
            horizon_days=60,
            created_at=datetime(2025, 12, 20, tzinfo=timezone.utc),
        )
        generated = generate_due_work_orders(
            conn,
            context,
            actor_id=context.actor_id,
            clock=FixedClock(datetime(2026, 1, 5, tzinfo=timezone.utc)),
        )
        self.assertEqual(2, len(generated))
        self.assertEqual(
            ["2025-12-20", "2025-12-30"],
            [item["scheduled_date"] for item in generated],
        )
        self.assertEqual(2, conn.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0])
        self.assertEqual(
            0,
            conn.execute(
                "SELECT COUNT(*) FROM maintenance_runs WHERE scheduled_date = '2026-01-09'"
            ).fetchone()[0],
            "no run for 2026-01-09",
        )

    def test_t3_simulated_interruption_recovery(self):
        conn = self._open_migrated()
        self._seed_rows(conn)
        context = self._context()
        plan = self._seed_plan(
            conn,
            context,
            interval_days=30,
            horizon_days=60,
            created_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        )
        generated = generate_due_work_orders(
            conn,
            context,
            actor_id=context.actor_id,
            clock=FixedClock(datetime(2026, 4, 15, tzinfo=timezone.utc)),
        )
        self.assertEqual(2, len(generated))
        victim = generated[0]["run_id"]
        with conn:
            conn.execute(
                "UPDATE maintenance_runs SET work_order_id = NULL,"
                " status = 'pending' WHERE id = ?",
                (victim,),
            )
        processed = process_pending_runs(
            conn,
            context,
            actor_id=context.actor_id,
            clock=FixedClock(datetime(2026, 4, 15, 0, 0, 1, tzinfo=timezone.utc)),
        )
        self.assertEqual(1, len(processed))
        self.assertEqual(2, conn.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0])
        self.assertEqual(
            ["generated", "generated"],
            [row["status"] for row in conn.execute(
                "SELECT status FROM maintenance_runs ORDER BY scheduled_date, id"
            ).fetchall()],
        )
        self.assertEqual(
            ["generated"],
            [row["status"] for row in conn.execute(
                "SELECT status FROM maintenance_runs WHERE id = ?", (victim,)
            ).fetchall()],
        )

    def test_t4_double_generation_at_date_boundary(self):
        conn = self._open_migrated()
        self._seed_rows(conn)
        context = self._context()
        self._seed_plan(
            conn,
            context,
            interval_days=30,
            horizon_days=60,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        first = generate_due_work_orders(
            conn,
            context,
            actor_id=context.actor_id,
            clock=FixedClock(datetime(2026, 2, 15, tzinfo=timezone.utc)),
        )
        self.assertEqual(2, len(first))
        second = generate_due_work_orders(
            conn,
            context,
            actor_id=context.actor_id,
            clock=FixedClock(datetime(2026, 2, 15, tzinfo=timezone.utc)),
        )
        self.assertEqual([], second)
        self.assertEqual(2, conn.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0])
        self.assertEqual(2, conn.execute("SELECT COUNT(*) FROM maintenance_runs").fetchone()[0])
