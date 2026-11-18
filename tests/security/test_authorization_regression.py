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


if __name__ == "__main__":
    unittest.main()
