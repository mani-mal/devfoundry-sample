"""Integration tests (T049/T050): maintenance plan service and due-date preview.

Runs the REAL shipped migrations against a temporary file database and
exercises the maintenance plan service plus its deterministic due-date
preview through public functions only. The only time source in every
test is an injected FixedClock, so month/year/leap-day boundaries are
byte-identical across runs.
"""

import os
import tempfile
import unittest
from datetime import datetime, timezone

from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError
from opsledger.core.migrations import migrate
from opsledger.assets import (
    create_site,
    create_asset,
    archive_asset,
    archive_site,
)
from opsledger.maintenance.plans import (
    ARCHIVED_ASSET_MESSAGE,
    PLAN_NOT_FOUND_MESSAGE,
    create_maintenance_plan,
    get_maintenance_plan,
    list_maintenance_plans,
    archive_maintenance_plan,
)
from opsledger.maintenance.preview import (
    PLAN_NOT_ACTIVE_MESSAGE,
    next_due_date,
    preview_due_dates,
)


class MaintenancePlanTest(unittest.TestCase):
    def _open_migrated(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda p=tmp.name: os.path.exists(p) and os.unlink(p))
        self.addCleanup(lambda: connect(tmp.name).close())
        conn = connect(tmp.name)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def _seed_organizations(self, conn):
        created_text = "2026-01-01T00:00:00Z"
        with conn:
            conn.execute(
                "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                ("org-aaa", "org-aaa", "Organization AAA", created_text),
            )
            conn.execute(
                "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                ("org-bbb", "org-bbb", "Organization BBB", created_text),
            )

    def _context(self, organization_id="org-aaa", actor_id="user-111"):
        return OrganizationContext(organization_id=organization_id, actor_id=actor_id)

    def _clock(self, *, year=2026, month=1, day=31, hour=12):
        return FixedClock(datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc))

    def _seed_site_and_asset(self, conn, context):
        self._seed_organizations(conn)
        base = self._clock(day=1)
        site = create_site(conn, context, code="hq", name="Headquarters", clock=base)
        asset = create_asset(
            conn, context, site_id=site["id"], tag="pump-01", name="Coolant pump",
            criticality="high", purchase_cost_cents=250000,
            clock=self._clock(day=1, hour=13),
        )
        return site, asset

    def _create_plan(self, conn, context, site, asset, **overrides):
        kwargs = {
            "site_id": site["id"],
            "asset_id": asset["id"],
            "name": "Monthly service",
            "description": "Routine monthly maintenance",
            "interval_days": 30,
            "horizon_days": 90,
            "clock": self._clock(day=31),
        }
        kwargs.update(overrides)
        return create_maintenance_plan(conn, context, **kwargs)

    def test_create_refuses_non_positive_interval_days(self):
        conn = self._open_migrated()
        site, asset = self._seed_site_and_asset(conn, self._context())
        for interval in (0, -1):
            with self.assertRaises(ValidationError) as caught:
                self._create_plan(conn, self._context(), site, asset, interval_days=interval)
            self.assertEqual("interval_days must be a positive integer", str(caught.exception))

    def test_create_enforces_bounded_horizon(self):
        conn = self._open_migrated()
        site, asset = self._seed_site_and_asset(conn, self._context())
        for horizon in (0, 367):
            with self.assertRaises(ValidationError) as caught:
                self._create_plan(conn, self._context(), site, asset, horizon_days=horizon)
            self.assertEqual(
                "horizon_days must be an integer between 1 and 366", str(caught.exception),
            )
        for horizon in (1, 366):
            plan = self._create_plan(conn, self._context(), site, asset, horizon_days=horizon)
            self.assertEqual(horizon, plan["horizon_days"])

    def test_create_refuses_archived_asset_and_site(self):
        conn = self._open_migrated()
        site, asset = self._seed_site_and_asset(conn, self._context())
        archived = archive_asset(conn, self._context(), asset_id=asset["id"], clock=self._clock(day=2))
        with self.assertRaises(ValidationError) as caught:
            self._create_plan(conn, self._context(), site, archived)
        self.assertEqual(ARCHIVED_ASSET_MESSAGE, str(caught.exception))

        spare = create_site(conn, self._context(), code="old", name="Old yard", clock=self._clock(day=1, hour=14))
        archived_site = archive_site(conn, self._context(), site_id=spare["id"], clock=self._clock(day=2))
        with self.assertRaises(ValidationError) as caught:
            self._create_plan(conn, self._context(), archived_site, asset)
        self.assertEqual("site is archived", str(caught.exception))

    def test_create_refuses_asset_on_different_site(self):
        conn = self._open_migrated()
        site, asset = self._seed_site_and_asset(conn, self._context())
        other = create_site(conn, self._context(), code="east", name="East depot", clock=self._clock(day=1, hour=15))
        with self.assertRaises(ValidationError) as caught:
            self._create_plan(conn, self._context(), other, asset)
        self.assertEqual("asset belongs to a different site", str(caught.exception))

    def test_create_refuses_non_string_name(self):
        conn = self._open_migrated()
        site, asset = self._seed_site_and_asset(conn, self._context())
        for name in (None, 7, ["x"]):
            with self.assertRaises(ValidationError) as caught:
                self._create_plan(conn, self._context(), site, asset, name=name)
            self.assertEqual("name is required", str(caught.exception))

    def test_create_returns_active_row_and_supports_lookup_listing(self):
        conn = self._open_migrated()
        context = self._context()
        site, asset = self._seed_site_and_asset(conn, context)
        plan = self._create_plan(conn, context, site, asset)
        self.assertEqual(1, plan["active"])
        self.assertEqual(1, plan["version"])
        self.assertEqual("Monthly service", plan["name"])
        found = get_maintenance_plan(conn, context, plan_id=plan["id"])
        self.assertEqual(plan["id"], found["id"])

        second = self._create_plan(conn, context, site, asset, name="Backup service")
        own = list_maintenance_plans(conn, context)
        self.assertEqual({plan["id"], second["id"]}, {row["id"] for row in own})
        archived = archive_maintenance_plan(conn, context, plan_id=second["id"], expected_version=1, clock=self._clock(day=1))
        self.assertEqual(1, len(list_maintenance_plans(conn, context, active_only=True)))
        self.assertEqual(2, len(list_maintenance_plans(conn, context)))

    def test_archive_lifecycle_and_version_conflicts(self):
        conn = self._open_migrated()
        context = self._context()
        site, asset = self._seed_site_and_asset(conn, context)
        plan = self._create_plan(conn, context, site, asset)
        archived = archive_maintenance_plan(conn, context, plan_id=plan["id"], expected_version=1, clock=self._clock(day=15))
        self.assertEqual(1, bool(archived["archived_at"]))
        self.assertEqual(0, archived["active"])
        self.assertEqual(2, archived["version"])
        self.assertEqual("2026-01-15T12:00:00Z", archived["archived_at"])
        with self.assertRaises(ConflictError) as caught:
            archive_maintenance_plan(conn, context, plan_id=plan["id"], expected_version=2, clock=self._clock(day=16))
        self.assertEqual("maintenance plan is archived", str(caught.exception))

        again = self._create_plan(conn, context, site, asset, name="Second plan")
        with self.assertRaises(ConflictError) as caught:
            archive_maintenance_plan(conn, context, plan_id=again["id"], expected_version=7, clock=self._clock(day=17))
        self.assertEqual("maintenance plan version conflict; refresh and retry", str(caught.exception))

    def test_get_missing_and_cross_organization_not_found_share_message(self):
        conn = self._open_migrated()
        context = self._context()
        site, asset = self._seed_site_and_asset(conn, context)
        plan = self._create_plan(conn, context, site, asset)
        with self.assertRaises(NotFoundError) as missing:
            get_maintenance_plan(conn, context, plan_id="mpl-missing")
        with self.assertRaises(NotFoundError) as cross:
            get_maintenance_plan(conn, self._context("org-bbb"), plan_id=plan["id"])
        self.assertEqual(PLAN_NOT_FOUND_MESSAGE, str(cross.exception))
        self.assertEqual(str(missing.exception), str(cross.exception))

    def test_preview_includes_anchor_and_rolls_over_february(self):
        conn = self._open_migrated()
        context = self._context()
        site, asset = self._seed_site_and_asset(conn, context)
        plan = self._create_plan(
            conn, context, site, asset,
            name="Anchored", description="February rollover",
            interval_days=30, horizon_days=90, clock=self._clock(day=31),
        )
        self.assertEqual("2026-01-31T12:00:00Z", plan["created_at"])
        due = preview_due_dates(conn, context, plan_id=plan["id"], clock=self._clock(day=31))
        self.assertIn("2026-01-31", due)
        self.assertIn("2026-03-02", due)
        self.assertIn("2026-04-01", due)
        self.assertLess(due.index("2026-01-31"), due.index("2026-03-02"))
        self.assertLess(due.index("2026-03-02"), due.index("2026-04-01"))

    def test_month_and_year_boundary(self):
        conn = self._open_migrated()
        context = self._context()
        site, asset = self._seed_site_and_asset(conn, context)
        plan = self._create_plan(
            conn, context, site, asset,
            name="Year end", description="Anchored 2025-12-15",
            interval_days=10, horizon_days=60, clock=self._clock(year=2025, month=12, day=15),
        )
        self.assertEqual("2025-12-15T12:00:00Z", plan["created_at"])
        due = preview_due_dates(conn, context, plan_id=plan["id"], clock=self._clock(year=2025, month=12, day=15))
        self.assertIn("2025-12-25", due)
        self.assertIn("2026-01-04", due)

    def test_leap_day_boundary(self):
        conn = self._open_migrated()
        context = self._context()
        site, asset = self._seed_site_and_asset(conn, context)
        leap_plan = self._create_plan(
            conn, context, site, asset,
            name="Leap year", description="Anchored 2028-02-28",
            interval_days=1, horizon_days=10, clock=self._clock(year=2028, month=2, day=28),
        )
        self.assertEqual("2028-02-28T12:00:00Z", leap_plan["created_at"])
        due = preview_due_dates(conn, context, plan_id=leap_plan["id"], clock=self._clock(year=2028, month=2, day=28))
        self.assertIn("2028-02-29", due)

        plain_plan = self._create_plan(
            conn, context, site, asset,
            name="Non leap", description="Anchored 2027-02-28",
            interval_days=1, horizon_days=10, clock=self._clock(year=2027, month=2, day=28),
        )
        self.assertEqual("2027-02-28T12:00:00Z", plain_plan["created_at"])
        plain_due = preview_due_dates(conn, context, plan_id=plain_plan["id"], clock=self._clock(year=2027, month=2, day=28))
        self.assertIn("2027-03-01", plain_due)
        self.assertNotIn("2027-02-29", plain_due)

    def test_horizon_bound_caps_preview(self):
        conn = self._open_migrated()
        context = self._context()
        site, asset = self._seed_site_and_asset(conn, context)
        plan = self._create_plan(
            conn, context, site, asset,
            name="Yearly", description="Horizon-inclusive preview",
            interval_days=366, horizon_days=366, clock=self._clock(month=1, day=1),
        )
        self.assertEqual("2026-01-01T12:00:00Z", plan["created_at"])
        due = preview_due_dates(conn, context, plan_id=plan["id"], clock=self._clock(month=1, day=1))
        self.assertEqual(["2026-01-01", "2027-01-02"], due)

    def test_preview_is_deterministic_under_fixed_clock(self):
        conn = self._open_migrated()
        context = self._context()
        site, asset = self._seed_site_and_asset(conn, context)
        plan = self._create_plan(conn, context, site, asset)
        first = preview_due_dates(conn, context, plan_id=plan["id"], clock=self._clock(day=31))
        second = preview_due_dates(conn, context, plan_id=plan["id"], clock=self._clock(day=31))
        self.assertEqual(first, second)

    def test_next_due_date_is_first_strictly_future_date(self):
        conn = self._open_migrated()
        context = self._context()
        site, asset = self._seed_site_and_asset(conn, context)
        plan = self._create_plan(
            conn, context, site, asset,
            name="Mid interval", description="Anchored 2026-02-01",
            interval_days=30, horizon_days=120, clock=self._clock(month=2, day=1),
        )
        due = preview_due_dates(conn, context, plan_id=plan["id"], clock=self._clock(month=2, day=1))
        self.assertIn("2026-03-03", due)
        next_date = next_due_date(conn, context, plan_id=plan["id"], clock=self._clock(month=2, day=20))
        self.assertEqual("2026-03-03", next_date)


if __name__ == "__main__":
    unittest.main()
