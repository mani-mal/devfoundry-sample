"""Integration tests (T052): maintenance outbox — persisted pending-run
processing with bounded retry.

These tests apply the REAL shipped migrations to a temporary file database
and then exercise :func:`opsledger.maintenance.outbox.process_pending_runs`
and :func:`opsledger.maintenance.outbox.outbox_events_for_run` against the
migrated schema — no CREATE TABLE anywhere in the test (every table comes
from the shipped migrations). Each processing call gets a DISTINCT
FixedClock instant from ``_tick_clock``; timestamps are asserted as UTC
deltas rather than absolute constants.

Forcing a failing attempt: the maintenance_runs foreign key onto
maintenance_plans makes a run pointing at a nonexistent plan invisible to
the processor (INNER JOIN in the runner's SELECT), so the failing attempt
is forced by archiving the plan's site — the bounded-retry behaviour under
test (stays 'pending', attempt incremented, backoff scheduled) remains the
service's own.
"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from opsledger.assets import create_asset, create_site
from opsledger.core.clock import FixedClock
from opsledger.core.context import OrganizationContext
from opsledger.core.db import connect
from opsledger.core.errors import NotFoundError
from opsledger.core.migrations import migrate
from opsledger.maintenance.outbox import (
    RETRY_EXHAUSTED_MESSAGE,
    RUN_NOT_FOUND_MESSAGE,
    outbox_events_for_run,
    process_pending_runs,
)
from opsledger.maintenance.plans import create_maintenance_plan

_CREATED_TEXT = "2026-11-06T12:00:00Z"
_BASE_INSTANT = datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)


def _parse_rfc3339(text):
    assert text.endswith("Z")
    return datetime.fromisoformat(text[:-1] + "+00:00")


class MaintenanceOutboxTests(unittest.TestCase):
    """Outbox tests for process_pending_runs on the real migrated schema."""

    def _tick_clock(self):
        self._instants = getattr(self, "_instants", 0) + 1
        return FixedClock(_BASE_INSTANT + timedelta(seconds=self._instants))

    def _context(self, organization_id="org-aaa", actor_id="user-1"):
        return OrganizationContext(organization_id=organization_id, actor_id=actor_id)

    def _open_migrated(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda: connect(tmp.name).close())
        conn = connect(tmp.name)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def _seed_identity(self, conn):
        with conn:
            conn.execute(
                "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                ("org-aaa", "org-aaa", "Organization AAA", _CREATED_TEXT),
            )
            conn.execute(
                "INSERT INTO users (id, email, display_name, created_at) VALUES (?, ?, ?, ?)",
                ("user-1", "tech@example.com", "Technician", _CREATED_TEXT),
            )

    def _seed_site_and_asset(self, conn):
        clock = self._tick_clock()
        site = create_site(conn, self._context(), code="main", name="Site A", clock=clock)
        asset = create_asset(
            conn,
            self._context(),
            site_id=site["id"],
            tag="pump-001",
            name="Asset pump-001",
            criticality="medium",
            purchase_cost_cents=10000,
            clock=clock,
        )
        return site, asset

    def _seed_plan(self, conn, site, asset):
        return create_maintenance_plan(
            conn,
            self._context(),
            site_id=site["id"],
            asset_id=asset["id"],
            name="Monthly pump service",
            description="Service the pump on a monthly interval",
            interval_days=30,
            horizon_days=120,
            clock=self._tick_clock(),
        )

    def _seed_pending_run(self, conn, plan, scheduled_date):
        with conn:
            conn.execute(
                "INSERT INTO maintenance_runs (id, organization_id, plan_id, scheduled_date,"
                " status, attempt_count, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, 'pending', 0, ?, ?)",
                (f"run-{scheduled_date}", "org-aaa", plan["id"], scheduled_date, _CREATED_TEXT, _CREATED_TEXT),
            )

    def _process(self, conn, clock=None):
        return process_pending_runs(
            conn,
            self._context(),
            actor_id="user-1",
            clock=clock if clock is not None else self._tick_clock(),
        )

    def test_process_pending_runs_completes_pending_runs_with_one_outbox_record(self):
        conn = self._open_migrated()
        self._seed_identity(conn)
        site, asset = self._seed_site_and_asset(conn)
        plan = self._seed_plan(conn, site, asset)
        self._seed_pending_run(conn, plan, "2026-11-20")
        self._seed_pending_run(conn, plan, "2026-12-20")

        processed = self._process(conn)

        self.assertEqual(2, len(processed))
        self.assertEqual(2, conn.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0])
        for entry, scheduled in ((processed[0], "2026-11-20"), (processed[1], "2026-12-20")):
            self.assertEqual(f"run-{scheduled}", entry["run_id"])
            self.assertEqual(scheduled, entry["scheduled_date"])
            self.assertEqual(1, entry["attempt"])
            self.assertIsNotNone(entry["work_order_id"])

        stored = {
            row["id"]: row
            for row in conn.execute("SELECT * FROM maintenance_runs").fetchall()
        }
        for entry in processed:
            row = stored[entry["run_id"]]
            self.assertEqual("generated", row["status"])
            self.assertEqual(entry["work_order_id"], row["work_order_id"])
            self.assertEqual(1, row["attempt_count"])
            self.assertIsNone(row["next_retry_at"])
            self.assertIsNone(row["last_error"])

        for entry in processed:
            events = outbox_events_for_run(conn, self._context(), run_id=entry["run_id"])
            self.assertEqual(1, len(events))
            event = events[0]
            self.assertEqual("maintenance.run_processed", event["operation"])
            self.assertEqual("maintenance_run", event["entity_type"])
            self.assertEqual(entry["run_id"], event["entity_id"])
            self.assertEqual("user-1", event["actor_id"])
            details = json.loads(event["details"])
            self.assertEqual({"work_order_id", "scheduled_date", "attempt"}, set(details))
            self.assertEqual(entry["work_order_id"], details["work_order_id"])
            self.assertEqual(entry["scheduled_date"], details["scheduled_date"])
            self.assertEqual(entry["attempt"], details["attempt"])

    def test_simulated_crash_retry_creates_no_duplicate_work_order(self):
        conn = self._open_migrated()
        self._seed_identity(conn)
        site, asset = self._seed_site_and_asset(conn)
        plan = self._seed_plan(conn, site, asset)
        self._seed_pending_run(conn, plan, "2026-11-20")

        self._process(conn)
        before = conn.execute(
            "SELECT * FROM maintenance_runs WHERE id = ?", ("run-2026-11-20",)
        ).fetchone()
        self.assertEqual("generated", before["status"])
        self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0])

        conn.execute(
            "UPDATE maintenance_runs SET work_order_id = NULL, status = 'pending' WHERE id = ?",
            ("run-2026-11-20",),
        )

        processed = self._process(conn)

        self.assertEqual(1, len(processed))
        after = conn.execute(
            "SELECT * FROM maintenance_runs WHERE id = ?", ("run-2026-11-20",)
        ).fetchone()
        self.assertEqual("generated", after["status"])
        self.assertEqual(before["work_order_id"], after["work_order_id"])
        self.assertEqual(2, after["attempt_count"])
        self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0])

        events = outbox_events_for_run(conn, self._context(), run_id="run-2026-11-20")
        self.assertEqual(2, len(events))
        self.assertEqual([1, 2], [json.loads(item["details"])["attempt"] for item in events])
        self.assertTrue(events[0]["created_at"] < events[1]["created_at"])

    def test_failing_attempt_stays_pending_with_retry_backoff(self):
        conn = self._open_migrated()
        self._seed_identity(conn)
        site, asset = self._seed_site_and_asset(conn)
        plan = self._seed_plan(conn, site, asset)
        self._seed_pending_run(conn, plan, "2026-11-20")

        with conn:
            conn.execute(
                "UPDATE sites SET archived_at = ? WHERE id = ?",
                ("2026-11-13T13:00:00Z", site["id"]),
            )

        clock = self._tick_clock()
        processed = process_pending_runs(conn, self._context(), actor_id="user-1", clock=clock)

        self.assertEqual([], processed)
        row = conn.execute(
            "SELECT * FROM maintenance_runs WHERE id = ?", ("run-2026-11-20",)
        ).fetchone()
        self.assertEqual("pending", row["status"])
        self.assertEqual(1, row["attempt_count"])
        self.assertTrue(row["last_error"])
        self.assertEqual(0, conn.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0])

        retry_at = _parse_rfc3339(row["next_retry_at"])
        self.assertEqual(timedelta(seconds=60), retry_at - clock.now())

    def test_retry_exhaustion_transitions_exhausted_run_to_failed(self):
        conn = self._open_migrated()
        self._seed_identity(conn)
        site, asset = self._seed_site_and_asset(conn)
        plan = self._seed_plan(conn, site, asset)
        self._seed_pending_run(conn, plan, "2026-11-20")

        with conn:
            conn.execute(
                "UPDATE maintenance_runs SET attempt_count = 3 WHERE id = ?",
                ("run-2026-11-20",),
            )

        self._process(conn)

        failed = conn.execute(
            "SELECT * FROM maintenance_runs WHERE id = ?", ("run-2026-11-20",)
        ).fetchone()
        self.assertEqual("failed", failed["status"])
        self.assertEqual(RETRY_EXHAUSTED_MESSAGE, failed["last_error"])
        self.assertEqual(3, failed["attempt_count"])
        self.assertEqual(0, conn.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0])

        self._process(conn)

        untouched = conn.execute(
            "SELECT * FROM maintenance_runs WHERE id = ?", ("run-2026-11-20",)
        ).fetchone()
        self.assertEqual("failed", untouched["status"])
        self.assertEqual(RETRY_EXHAUSTED_MESSAGE, untouched["last_error"])
        self.assertEqual(3, untouched["attempt_count"])

    def test_outbox_events_for_run_scoping_and_missing_run(self):
        conn = self._open_migrated()
        self._seed_identity(conn)
        site, asset = self._seed_site_and_asset(conn)
        plan = self._seed_plan(conn, site, asset)
        self._seed_pending_run(conn, plan, "2026-11-20")

        self._process(conn)

        events = outbox_events_for_run(conn, self._context(), run_id="run-2026-11-20")
        self.assertEqual(1, len(events))
        self.assertEqual("maintenance.run_processed", events[0]["operation"])
        self.assertEqual("maintenance_run", events[0]["entity_type"])
        self.assertEqual("run-2026-11-20", events[0]["entity_id"])
        self.assertEqual("user-1", events[0]["actor_id"])

        with self.assertRaises(NotFoundError) as missing:
            outbox_events_for_run(conn, self._context(), run_id="run-missing")
        self.assertEqual(RUN_NOT_FOUND_MESSAGE, str(missing.exception))

        with conn:
            conn.execute(
                "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                ("org-bbb", "org-bbb", "Organization BBB", _CREATED_TEXT),
            )
        with self.assertRaises(NotFoundError) as foreign:
            outbox_events_for_run(conn, self._context("org-bbb"), run_id="run-2026-11-20")
        self.assertEqual(RUN_NOT_FOUND_MESSAGE, str(foreign.exception))


if __name__ == "__main__":
    unittest.main()
