"""Integration tests (T060): READ-ONLY bounded CSV export of work orders.

These tests apply the REAL shipped migrations to a temporary file database
and exercise :func:`opsledger.reporting.csv_export.export_work_orders`
against that migrated schema — no CREATE TABLE anywhere, mirroring the
migrate-a-temp-db setup style. Each behaviour and boundary is covered: the
``export.read`` permission gate before any query, the malformed
authorization context, the exact seven-column header, the stable
``created_at, id`` row order, formula-injection escaping, organization
scoping, and the 1000-row export bound.
"""

import csv
import io
import os
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from opsledger.assets import create_asset, create_site
from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect, transaction
from opsledger.core.errors import PermissionDeniedError, ValidationError
from opsledger.core.migrations import migrate
from opsledger.reporting.csv_export import CSV_HEADER, export_work_orders
from opsledger.workorders import create_work_order
from opsledger.workorders.transitions import transition_work_order


@dataclass(frozen=True)
class ReportingContext(OrganizationContext):
    """Frozen export context: an OrganizationContext carrying one role."""

    role: str = "technician"


class CsvExportTests(unittest.TestCase):
    """Integration tests for export_work_orders() on the real schema."""

    def setUp(self):
        self._clock_tick = 0

    def _open_migrated(self):
        """Open a temporary file database with the REAL shipped migrations."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda p=tmp.name: os.path.exists(p) and os.unlink(p))
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

    def _seed_user(self, conn, user_id, email):
        with transaction(conn) as tx:
            tx.execute(
                "INSERT OR IGNORE INTO users (id, email, display_name, created_at)"
                " VALUES (?, ?, ?, ?)",
                (
                    user_id,
                    email,
                    "Technician " + user_id,
                    "2026-11-06T12:00:00Z",
                ),
            )

    def _tick_clock(self):
        """Each call returns a NEW clock one second later."""
        self._clock_tick += 1
        return FixedClock(
            datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)
            + timedelta(seconds=self._clock_tick)
        )

    def _seed_site_and_asset(self, conn, context):
        site = create_site(conn, context, code="main", name="Main site", clock=self._tick_clock())
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
        return site, asset

    def test_export_requires_export_read_permission(self):
        conn = self._open_migrated()
        self._seed_organization(conn, "org-aaa")
        self._seed_user(conn, "user-111", "user-111@example.com")
        context = ReportingContext(organization_id="org-aaa")

        exported = export_work_orders(conn, context, actor=ReportingContext(organization_id="org-aaa", role="auditor"))
        self.assertIsInstance(exported, str)
        rows = list(csv.reader(io.StringIO(exported)))
        self.assertEqual([CSV_HEADER], rows)

        for role in ("admin", "supervisor", "technician", "purchasing"):
            with self.assertRaises(PermissionDeniedError):
                export_work_orders(
                    conn,
                    context,
                    actor=ReportingContext(organization_id="org-aaa", role=role),
                )

        with self.assertRaises(ValidationError):
            export_work_orders(
                conn, context, actor=ReportingContext(organization_id="org-aaa", role=None)
            )
        with self.assertRaises(ValidationError):
            export_work_orders(
                conn, context, actor=OrganizationContext(organization_id="org-aaa")
            )

    def test_csv_header_is_exact(self):
        self.assertEqual(
            [
                "work_order_id",
                "number",
                "title",
                "status",
                "priority",
                "asset_id",
                "created_at",
            ],
            CSV_HEADER,
        )

    def test_export_renders_rows_in_stable_order(self):
        conn = self._open_migrated()
        self._seed_organization(conn, "org-aaa")
        self._seed_user(conn, "user-111", "user-111@example.com")
        context = ReportingContext(organization_id="org-aaa")
        site, asset = self._seed_site_and_asset(conn, context)

        first = create_work_order(
            conn,
            context,
            site_id=site["id"],
            asset_id=asset["id"],
            number="WO-0001",
            title="Fix pump",
            description="Pump seized overnight",
            priority="high",
            requester_id="user-111",
            clock=self._tick_clock(),
        )
        second = create_work_order(
            conn,
            context,
            site_id=site["id"],
            asset_id=asset["id"],
            number="WO-0002",
            title="Grease bearing",
            description="Bearing runs hot",
            priority="low",
            requester_id="user-111",
            clock=self._tick_clock(),
        )
        transition_work_order(
            conn,
            context,
            work_order_id=second["id"],
            to_status="assigned",
            expected_version=1,
            reason="assign technician",
            actor_id="user-111",
            clock=self._tick_clock(),
        )
        transition_work_order(
            conn,
            context,
            work_order_id=second["id"],
            to_status="in_progress",
            expected_version=2,
            reason="start work",
            actor_id="user-111",
            clock=self._tick_clock(),
        )

        exported = export_work_orders(conn, context, actor=ReportingContext(organization_id="org-aaa", role="auditor"))
        rows = list(csv.reader(io.StringIO(exported)))

        self.assertEqual(CSV_HEADER, rows[0])
        self.assertEqual(3, len(rows))
        self.assertIn("WO-0001", rows[1])
        self.assertIn("Fix pump", rows[1])
        self.assertIn("WO-0002", rows[2])
        self.assertEqual(first["id"], rows[1][0])
        self.assertEqual(second["id"], rows[2][0])
        self.assertEqual("open", rows[1][3])
        self.assertEqual("in_progress", rows[2][3])
        self.assertRegex(rows[1][6], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertRegex(rows[2][6], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_export_escapes_formula_injection(self):
        conn = self._open_migrated()
        self._seed_organization(conn, "org-aaa")
        self._seed_user(conn, "user-111", "user-111@example.com")
        context = ReportingContext(organization_id="org-aaa")
        site, asset = self._seed_site_and_asset(conn, context)

        titled = (
            ("WO-2101", "=SUM(A1)"),
            ("WO-2102", "+cmd"),
            ("WO-2103", "@x"),
            ("WO-2104", "-5 items"),
            ("WO-2105", "safe title"),
        )
        for number, title in titled:
            create_work_order(
                conn,
                context,
                site_id=site["id"],
                asset_id=asset["id"],
                number=number,
                title=title,
                description="recorded note",
                priority="medium",
                requester_id="user-111",
                clock=self._tick_clock(),
            )

        exported = export_work_orders(conn, context, actor=ReportingContext(organization_id="org-aaa", role="auditor"))
        rows = list(csv.reader(io.StringIO(exported)))

        self.assertEqual(CSV_HEADER, rows[0])
        by_number = {row[1]: row for row in rows[1:]}
        self.assertEqual("'=SUM(A1)", by_number["WO-2101"][2])
        self.assertEqual("'+cmd", by_number["WO-2102"][2])
        self.assertEqual("'@x", by_number["WO-2103"][2])
        self.assertEqual("'-5 items", by_number["WO-2104"][2])
        self.assertEqual("safe title", by_number["WO-2105"][2])
        for cell in rows[0]:
            self.assertFalse(cell.startswith("'"))

    def test_export_is_org_scoped(self):
        conn = self._open_migrated()
        self._seed_organization(conn, "org-aaa")
        self._seed_user(conn, "user-111", "user-111@example.com")
        context_a = ReportingContext(organization_id="org-aaa")
        site_a, asset_a = self._seed_site_and_asset(conn, context_a)
        mine = create_work_order(
            conn,
            context_a,
            site_id=site_a["id"],
            asset_id=asset_a["id"],
            number="WO-0001",
            title="Fix pump",
            description="Pump seized overnight",
            priority="high",
            requester_id="user-111",
            clock=self._tick_clock(),
        )

        self._seed_organization(conn, "org-bbb")
        other = ReportingContext(organization_id="org-bbb")
        other_site = create_site(conn, other, code="north", name="North site", clock=self._tick_clock())
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
        theirs = create_work_order(
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

        own = export_work_orders(conn, context_a, actor=ReportingContext(organization_id="org-aaa", role="auditor"))
        own_rows = list(csv.reader(io.StringIO(own)))
        self.assertEqual(2, len(own_rows))
        self.assertEqual(mine["id"], own_rows[1][0])
        self.assertIn("WO-0001", own_rows[1])
        for row in own_rows[1:]:
            self.assertNotIn("WO-9001", row)

        reverse = export_work_orders(conn, other, actor=ReportingContext(organization_id="org-aaa", role="auditor"))
        reverse_rows = list(csv.reader(io.StringIO(reverse)))
        self.assertEqual(2, len(reverse_rows))
        self.assertEqual(theirs["id"], reverse_rows[1][0])
        self.assertIn("WO-9001", reverse_rows[1])
        for row in reverse_rows[1:]:
            self.assertNotIn("WO-0001", row)

    def test_export_is_bounded_at_1000_rows(self):
        conn = self._open_migrated()
        self._seed_organization(conn, "org-aaa")
        self._seed_user(conn, "user-111", "user-111@example.com")
        context = ReportingContext(organization_id="org-aaa")
        site, asset = self._seed_site_and_asset(conn, context)

        created = []
        for index in range(1005):
            created.append(
                create_work_order(
                    conn,
                    context,
                    site_id=site["id"],
                    asset_id=asset["id"],
                    number=f"WO-{index + 1:04d}",
                    title=f"Job {index + 1}",
                    description="bounded note",
                    priority="medium",
                    requester_id="user-111",
                    clock=self._tick_clock(),
                )
            )

        exported = export_work_orders(conn, context, actor=ReportingContext(organization_id="org-aaa", role="auditor"))
        rows = list(csv.reader(io.StringIO(exported)))

        self.assertEqual(1001, len(rows))
        self.assertEqual(created[0]["id"], rows[1][0])
        self.assertEqual("WO-0001", rows[1][1])

    def test_export_quoting_survives_commas_and_newlines_is_csv_module_domain(self):
        conn = self._open_migrated()
        self._seed_organization(conn, "org-aaa")
        self._seed_user(conn, "user-111", "user-111@example.com")
        context = ReportingContext(organization_id="org-aaa")
        site, asset = self._seed_site_and_asset(conn, context)
        create_work_order(
            conn,
            context,
            site_id=site["id"],
            asset_id=asset["id"],
            number="WO-0001",
            title="Fix, then check",
            description="comma note",
            priority="medium",
            requester_id="user-111",
            clock=self._tick_clock(),
        )

        exported = export_work_orders(conn, context, actor=ReportingContext(organization_id="org-aaa", role="auditor"))
        rows = list(csv.reader(io.StringIO(exported)))

        self.assertEqual(CSV_HEADER, rows[0])
        self.assertEqual("Fix, then check", rows[1][2])


if __name__ == "__main__":
    unittest.main()
