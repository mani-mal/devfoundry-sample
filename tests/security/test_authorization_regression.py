"""T074 authorization regression tests (spec §7.3/M2/M10; part 1 of 2).

Every declared role × aggregate pair is covered here: dashboard,
asset_cost_report, search, export_work_orders, query_events and
count_events each gate on one permission, so every (aggregate, role)
cell is asserted to either return normally or raise PermissionDeniedError.
The org-scoping and purchasing-approver tests are a separate follow-up task that ADDS methods to this file.
"""

import os
import sys
import pathlib
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from opsledger.assets import create_asset, create_site  # noqa: E402
from opsledger.audit.queries import count_events, query_events  # noqa: E402
from opsledger.core import OrganizationContext  # noqa: E402
from opsledger.core.clock import FixedClock  # noqa: E402
from opsledger.core.db import connect, transaction  # noqa: E402
from opsledger.core.errors import PermissionDeniedError, ValidationError  # noqa: E402
from opsledger.core.migrations import migrate  # noqa: E402
from opsledger.identity import permissions  # noqa: E402
from opsledger.reporting.cost_report import asset_cost_report  # noqa: E402
from opsledger.reporting.csv_export import export_work_orders  # noqa: E402
from opsledger.reporting.dashboard import dashboard  # noqa: E402
from opsledger.reporting.search import search  # noqa: E402

ROLES = ("admin", "supervisor", "technician", "purchasing", "auditor")
BASE_PERMISSIONS = permissions.BASE_PERMISSIONS


class _Actor:
    """Minimal authorization context: role/actor_id attributes."""

    def __init__(self, role, actor_id="u-1"):
        self.role = role
        self.actor_id = actor_id


class AuthorizationRegressionTests(unittest.TestCase):
    """Regression coverage for the T074 authorization matrix (part 1)."""

    def setUp(self):
        self._clock_step = 0

    def _migrated_conn(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        path = tmp.name
        self.addCleanup(lambda p=path: os.path.exists(p) and os.unlink(p))
        tmp.close()
        conn = connect(path)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def _tick_clock(self):
        """Each call one second later from 2026-11-18T12:00:00Z."""
        self._clock_step += 1
        return FixedClock(
            datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc)
            + timedelta(seconds=self._clock_step)
        )

    def _seed_org_fixture(self, conn, organization_id):
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
        context = OrganizationContext(organization_id=organization_id)
        site = create_site(conn, context, code="hq", name="Headquarters", clock=self._tick_clock())
        create_asset(conn, context, site_id=site["id"], tag="pump-1", name="Pump 1",
                     criticality="low", purchase_cost_cents=2500, clock=self._tick_clock())

    def test_every_role_aggregate_pair_matches_base_permissions(self):
        conn = self._migrated_conn()
        self._seed_org_fixture(conn, "org-auth")
        context = OrganizationContext(organization_id="org-auth")
        cases = [
            (dashboard, {}, "reporting.read"),
            (asset_cost_report, {}, "reporting.read"),
            (search, {"query": "pump"}, "reporting.read"),
            (export_work_orders, {}, "export.read"),
            (query_events, {}, "audit.read"),
            (count_events, {}, "audit.read"),
        ]
        cells = 0
        for fn, kwargs, permission in cases:
            for role in ROLES:
                try:
                    fn(conn, context, actor=_Actor(role), **kwargs)
                    verdict = "A"
                except PermissionDeniedError:
                    verdict = "D"
                self.assertEqual(verdict, "A" if permission in BASE_PERMISSIONS[role] else "D")
                cells += 1
        self.assertEqual(cells, 30)

    def test_permission_helpers_and_malformed_contexts(self):
        conn = self._migrated_conn()
        context = OrganizationContext(organization_id="org-helpers")
        approve = permissions.PURCHASE_APPROVE_PERMISSION
        for role in ROLES:
            actor = _Actor(role)
            for permission in ("reporting.read", "export.read", "audit.read", approve):
                self.assertEqual(permissions.has_permission(actor, permission), permission in BASE_PERMISSIONS[role])
        self.assertTrue(permissions.has_permission(_Actor("auditor"), approve, explicit_grants=[approve]))
        self.assertFalse(permissions.has_permission(_Actor("auditor"), approve, explicit_grants=[]))
        self.assertEqual(
            permissions.effective_permissions("auditor", explicit_grants=["purchase.approve"]),
            BASE_PERMISSIONS["auditor"] | {approve},
        )
        with self.assertRaises(ValidationError):
            permissions.effective_permissions("no-such-role")
        self_actor = _Actor("auditor", actor_id="u-1")
        with self.assertRaises(PermissionDeniedError) as denied:
            permissions.assert_not_self_approval(self_actor, "u-1")
        self.assertEqual(str(denied.exception), "self-approval is not permitted")
        permissions.assert_not_self_approval(self_actor, "u-2")
        for hostile in (None, "admin", 42, _Actor("unknown"), _Actor(123)):
            with self.assertRaises(ValidationError) as raised:
                dashboard(conn, context, actor=hostile)
            self.assertEqual(str(str(raised.exception)), "malformed authorization context")
            self.assertNotIsInstance(raised.exception, PermissionDeniedError)

    def test_org_scoping_no_cross_organization_leak(self):
        from opsledger.assets.updates import update_asset_audited

        conn = self._migrated_conn()
        self._seed_org_fixture(conn, "org-a")
        self._seed_org_fixture(conn, "org-b")
        site_a = conn.execute("SELECT id FROM sites WHERE organization_id = ?", ("org-a",)).fetchone()["id"]
        site_b = conn.execute("SELECT id FROM sites WHERE organization_id = ?", ("org-b",)).fetchone()["id"]
        context_a = OrganizationContext(organization_id="org-a")
        context_b = OrganizationContext(organization_id="org-b")
        asset_a2 = create_asset(conn, context_a, site_id=site_a, tag="pump-a", name="Pump A",
                                criticality="low", purchase_cost_cents=3000, clock=self._tick_clock())
        asset_b2 = create_asset(conn, context_b, site_id=site_b, tag="pump-b", name="Pump B",
                                criticality="low", purchase_cost_cents=3000, clock=self._tick_clock())
        pump1_a = conn.execute("SELECT id FROM assets WHERE organization_id = ? AND tag = 'pump-1'", ("org-a",)).fetchone()["id"]
        pump1_b = conn.execute("SELECT id FROM assets WHERE organization_id = ? AND tag = 'pump-1'", ("org-b",)).fetchone()["id"]
        update_asset_audited(conn, context_a, asset_id=pump1_a, expected_version=1, name="Pump One", clock=self._tick_clock())
        update_asset_audited(conn, context_b, asset_id=pump1_b, expected_version=1, name="Pump One B", clock=self._tick_clock())
        actor_a = _Actor("auditor", actor_id="ua-1")
        actor_b = _Actor("auditor", actor_id="ub-1")
        ids_a = {row["id"] for row in search(conn, context_a, actor=actor_a, query="pump")["assets"]}
        ids_b = {row["id"] for row in search(conn, context_b, actor=actor_b, query="pump")["assets"]}
        self.assertEqual(len(ids_a), 2)
        self.assertEqual(len(ids_b), 2)
        report_ids_a = {row["asset_id"] for row in asset_cost_report(conn, context_a, actor=actor_a)}
        report_ids_b = {row["asset_id"] for row in asset_cost_report(conn, context_b, actor=actor_b)}
        self.assertEqual(len(report_ids_a), 2)
        self.assertEqual(len(report_ids_b), 2)
        self.assertTrue(report_ids_a.isdisjoint(ids_b))
        self.assertTrue(report_ids_b.isdisjoint(ids_a))
        search_ids_a = {row["id"] for row in search(conn, context_a, actor=actor_a, query="pump")["assets"]}
        search_ids_b = {row["id"] for row in search(conn, context_b, actor=actor_b, query="pump")["assets"]}
        self.assertTrue(search_ids_a.isdisjoint(ids_b))
        self.assertTrue(search_ids_b.isdisjoint(ids_a))
        export_a = export_work_orders(conn, context_a, actor=actor_a)
        export_b = export_work_orders(conn, context_b, actor=actor_b)
        self.assertNotIn("pump-b", export_a)
        self.assertNotIn("Pump B", export_a)
        self.assertNotIn("pump-a", export_b)
        self.assertNotIn("Pump A", export_b)
        events_a = query_events(conn, context_a, actor=actor_a)
        events_b = query_events(conn, context_b, actor=actor_b)
        self.assertEqual(len(events_a), 1)
        self.assertEqual(len(events_b), 1)
        self.assertEqual(events_a[0]["entity_id"], pump1_a)
        self.assertEqual(events_b[0]["entity_id"], pump1_b)
        self.assertNotIn("organization_id", events_a[0])
        self.assertEqual(count_events(conn, context_a, actor=actor_a), 1)
        self.assertEqual(count_events(conn, context_b, actor=actor_b), 1)
        self.assertEqual(dashboard(conn, context_a, actor=actor_a)["assets"]["total"], 2)
        self.assertEqual(dashboard(conn, context_b, actor=actor_b)["assets"]["total"], 2)


if __name__ == "__main__":
    unittest.main()
