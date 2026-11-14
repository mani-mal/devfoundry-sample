"""Integration tests (T025b): work-order create service.

These tests apply the REAL shipped migrations to a temporary file database
and then exercise :func:`opsledger.workorders.create_work_order` against
that migrated schema — no CREATE TABLE anywhere in the test. Acceptance
(spec M4/T025): asset, site and requester context consistent — the create
is scoped to an owned site and its asset, duplicates are per organization,
and missing/cross-organization references surface the same NotFoundError.
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
from opsledger.workorders import (
    DUPLICATE_WORK_ORDER_NUMBER_MESSAGE,
    create_work_order,
)


class WorkOrderCreateTests(unittest.TestCase):
    """Integration tests for create_work_order on the real migrated schema."""

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

    def _context(self, organization_id):
        return OrganizationContext(organization_id=organization_id)

    def _seed_site_and_asset(self, conn, tag="pump-001"):
        clock = FixedClock(datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc))
        self._seed_organizations(conn)
        site_a = create_site(
            conn,
            self._context("org-aaa"),
            code="main",
            name="Site A",
            clock=clock,
        )
        site_b = create_site(
            conn,
            self._context("org-bbb"),
            code="main",
            name="Site B",
            clock=clock,
        )
        asset_a = create_asset(
            conn,
            self._context("org-aaa"),
            site_id=site_a["id"],
            tag=tag,
            name="Asset " + tag,
            criticality="medium",
            purchase_cost_cents=10000,
            clock=clock,
        )
        return site_a, site_b, asset_a

    def _create_work_order(self, conn, site_id, asset_id, number="wo-001", organization_id="org-aaa"):
        return create_work_order(
            conn,
            self._context(organization_id),
            site_id=site_id,
            asset_id=asset_id,
            number=number,
            title="Rebuild pump",
            description="Full rebuild of pump 001",
            priority="high",
            requester_id="user-111",
            clock=FixedClock(datetime(2026, 11, 13, 15, 0, 0, tzinfo=timezone.utc)),
        )

    def test_t1_create_happy_path(self):
        conn = self._open_migrated()
        site_a, _, asset_a = self._seed_site_and_asset(conn)
        row = self._create_work_order(conn, site_a["id"], asset_a["id"])
        self.assertEqual("wor-", row["id"][:4])
        self.assertEqual("open", row["status"])
        self.assertEqual(1, row["version"])
        self.assertEqual("wo-001", row["number"])
        self.assertEqual("high", row["priority"])
        self.assertEqual("2026-11-13T15:00:00Z", row["created_at"])
        self.assertIsNone(row["archived_at"])

    def test_t2_same_org_duplicate_number_conflict(self):
        conn = self._open_migrated()
        site_a, _, asset_a = self._seed_site_and_asset(conn)
        self._create_work_order(conn, site_a["id"], asset_a["id"], number="wo-100")
        with self.assertRaises(ConflictError) as caught:
            self._create_work_order(conn, site_a["id"], asset_a["id"], number="wo-100")
        self.assertEqual(DUPLICATE_WORK_ORDER_NUMBER_MESSAGE, str(caught.exception))

    def test_t3_same_number_other_organization_allowed(self):
        conn = self._open_migrated()
        site_a, site_b, asset_a = self._seed_site_and_asset(conn)
        self._create_work_order(conn, site_a["id"], asset_a["id"], number="wo-100")
        asset_b = create_asset(
            conn,
            self._context("org-bbb"),
            site_id=site_b["id"],
            tag="pump-002",
            name="Asset pump-002",
            criticality="low",
            purchase_cost_cents=5000,
            clock=FixedClock(datetime(2026, 11, 13, 12, 30, 0, tzinfo=timezone.utc)),
        )
        row_b = self._create_work_order(conn, site_b["id"], asset_b["id"], number="wo-100", organization_id="org-bbb")
        self.assertEqual("org-bbb", row_b["organization_id"])

    def test_t4_cross_organization_site_not_found(self):
        conn = self._open_migrated()
        site_a, site_b, asset_a = self._seed_site_and_asset(conn)
        with self.assertRaises(NotFoundError):
            self._create_work_order(conn, site_b["id"], asset_a["id"])

    def test_t5_missing_asset_not_found(self):
        conn = self._open_migrated()
        site_a, _, _ = self._seed_site_and_asset(conn)
        with self.assertRaises(NotFoundError):
            self._create_work_order(conn, site_a["id"], "asset-missing")


if __name__ == "__main__":
    unittest.main()
