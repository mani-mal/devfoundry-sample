"""Integration tests (T028b): work-order checklist service.

These tests apply the REAL shipped migrations to a temporary file database
and then exercise :mod:`opsledger.workorders.checklists` against that
migrated schema — no CREATE TABLE anywhere in the test. Acceptance (spec
M4/T028): an incomplete mandatory item blocks completion; completing the
item clears the block; optional items never block; double completion and
bad input are refused.
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
from opsledger.workorders.checklists import (
    ITEM_ALREADY_COMPLETED_MESSAGE,
    add_checklist_item,
    checklist_completion_blocked,
    complete_checklist_item,
    list_checklist_items,
)


class ChecklistTests(unittest.TestCase):
    """Integration tests for the checklist service on the real migrated schema."""

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

    def _add(self, conn, work_order, label, mandatory, hour=15):
        return add_checklist_item(
            conn, self._context(), work_order_id=work_order["id"], label=label,
            mandatory=mandatory, clock=FixedClock(datetime(2026, 11, 13, hour, 0, 0, tzinfo=timezone.utc)),
        )

    def _complete(self, conn, item_id, hour=16):
        return complete_checklist_item(
            conn, self._context(), item_id=item_id,
            clock=FixedClock(datetime(2026, 11, 13, hour, 0, 0, tzinfo=timezone.utc)),
        )

    def test_t1_add_mandatory_and_optional_items(self):
        conn = self._open_migrated()
        _, _, work_order = self._seed_work_order(conn)
        mandatory_item = self._add(conn, work_order, "drain oil", True)
        optional_item = self._add(conn, work_order, "photo", False)
        self.assertEqual("cli-", mandatory_item["id"][:4])
        self.assertEqual(1, mandatory_item["mandatory"])
        self.assertEqual(0, optional_item["mandatory"])
        self.assertIsNone(mandatory_item["completed_at"])

    def test_t2_open_mandatory_item_blocks_completion(self):
        conn = self._open_migrated()
        _, _, work_order = self._seed_work_order(conn)
        self._add(conn, work_order, "drain oil", True)
        self._add(conn, work_order, "photo", False)
        self.assertEqual(["drain oil"], checklist_completion_blocked(conn, self._context(), work_order_id=work_order["id"]))

    def test_t3_completed_mandatory_item_clears_block(self):
        conn = self._open_migrated()
        _, _, work_order = self._seed_work_order(conn)
        item = self._add(conn, work_order, "drain oil", True)
        self._add(conn, work_order, "photo", False)
        completed = self._complete(conn, item["id"])
        self.assertIsNotNone(completed["completed_at"])
        self.assertEqual([], checklist_completion_blocked(conn, self._context(), work_order_id=work_order["id"]))

    def test_t4_optional_item_never_blocks(self):
        conn = self._open_migrated()
        _, _, work_order = self._seed_work_order(conn)
        self._add(conn, work_order, "photo", False)
        self.assertEqual([], checklist_completion_blocked(conn, self._context(), work_order_id=work_order["id"]))

    def test_t5_double_completion_conflict(self):
        conn = self._open_migrated()
        _, _, work_order = self._seed_work_order(conn)
        item = self._add(conn, work_order, "drain oil", True)
        self._complete(conn, item["id"])
        with self.assertRaises(ConflictError) as caught:
            self._complete(conn, item["id"])
        self.assertEqual(ITEM_ALREADY_COMPLETED_MESSAGE, str(caught.exception))
