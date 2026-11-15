"""Integration tests (T027b): work-order transition service.

These tests apply the REAL shipped migrations to a temporary file database
and then exercise :func:`opsledger.workorders.transitions.transition_work_order`
against that migrated schema — no CREATE TABLE anywhere in the test.
Acceptance (spec M4/T027): all allowed and forbidden state pairs exercised;
each transition appends one event row and one audit row in the same
transaction; stale versions are refused with nothing stored.
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
from opsledger.workorders.transitions import (
    INVALID_TRANSITION_MESSAGE,
    STALE_WORK_ORDER_VERSION_MESSAGE,
    TRANSITION_REASON_REQUIRED_MESSAGE,
    transition_work_order,
)


class TransitionTests(unittest.TestCase):
    """Integration tests for transition_work_order on the real migrated schema."""

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

    def _transition(self, conn, work_order, to_status, expected_version, reason=None):
        return transition_work_order(
            conn, self._context(), work_order_id=work_order["id"], to_status=to_status,
            expected_version=expected_version, reason=reason, actor_id="user-111",
            clock=FixedClock(datetime(2026, 11, 13, 15, 0, 0, tzinfo=timezone.utc)),
        )

    def _event_count(self, conn, work_order_id):
        return conn.execute(
            "SELECT COUNT(*) FROM work_order_events WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()[0]

    def _audit_count(self, conn, entity_id):
        return conn.execute(
            "SELECT COUNT(*) FROM audit_events WHERE entity_id = ? AND entity_type = 'work_order'",
            (entity_id,),
        ).fetchone()[0]

    def test_t1_open_to_assigned_appends_event_and_audit(self):
        conn = self._open_migrated()
        _, _, work_order = self._seed_work_order(conn)
        row = self._transition(conn, work_order, "assigned", 1)
        self.assertEqual("assigned", row["status"])
        self.assertEqual(2, row["version"])
        self.assertEqual(1, self._event_count(conn, work_order["id"]))
        self.assertEqual(1, self._audit_count(conn, work_order["id"]))

    def test_t2_forbidden_pair_open_to_completed_conflict(self):
        conn = self._open_migrated()
        _, _, work_order = self._seed_work_order(conn)
        with self.assertRaises(ConflictError) as caught:
            self._transition(conn, work_order, "completed", 1)
        self.assertEqual(INVALID_TRANSITION_MESSAGE, str(caught.exception))

    def test_t3_block_without_reason_validation_error(self):
        conn = self._open_migrated()
        _, _, work_order = self._seed_work_order(conn)
        self._transition(conn, work_order, "assigned", 1)
        self._transition(conn, work_order, "in_progress", 2)
        with self.assertRaises(ValidationError) as caught:
            self._transition(conn, work_order, "blocked", 3)
        self.assertEqual(TRANSITION_REASON_REQUIRED_MESSAGE, str(caught.exception))

    def test_t4_block_with_reason_then_unblock(self):
        conn = self._open_migrated()
        _, _, work_order = self._seed_work_order(conn)
        self._transition(conn, work_order, "assigned", 1)
        self._transition(conn, work_order, "in_progress", 2)
        row = self._transition(conn, work_order, "blocked", 3, reason="waiting parts")
        self.assertEqual("blocked", row["status"])
        row = self._transition(conn, work_order, "in_progress", 4, reason="parts arrived")
        self.assertEqual("in_progress", row["status"])

    def test_t5_stale_version_conflict_nothing_stored(self):
        conn = self._open_migrated()
        _, _, work_order = self._seed_work_order(conn)
        self._transition(conn, work_order, "assigned", 1)
        events_before = self._event_count(conn, work_order["id"])
        audit_before = self._audit_count(conn, work_order["id"])
        with self.assertRaises(ConflictError) as caught:
            self._transition(conn, work_order, "in_progress", 1)
        self.assertEqual(STALE_WORK_ORDER_VERSION_MESSAGE, str(caught.exception))
        self.assertEqual(events_before, self._event_count(conn, work_order["id"]))
        self.assertEqual(audit_before, self._audit_count(conn, work_order["id"]))

    def test_t6_full_open_to_close_to_reopen_walk(self):
        conn = self._open_migrated()
        _, _, work_order = self._seed_work_order(conn)
        self._transition(conn, work_order, "assigned", 1)
        self._transition(conn, work_order, "in_progress", 2)
        self._transition(conn, work_order, "completed", 3)
        row = self._transition(conn, work_order, "closed", 4)
        self.assertEqual("closed", row["status"])
        row = self._transition(conn, work_order, "open", 5, reason="reopen")
        self.assertEqual("open", row["status"])
        self.assertEqual(6, row["version"])
        self.assertEqual(5, self._event_count(conn, work_order["id"]))

    def test_t7_cancelled_is_terminal(self):
        conn = self._open_migrated()
        _, _, work_order = self._seed_work_order(conn)
        row = self._transition(conn, work_order, "cancelled", 1, reason="duplicate request")
        self.assertEqual("cancelled", row["status"])
        with self.assertRaises(ConflictError):
            self._transition(conn, work_order, "open", 2)

    def test_t8_missing_work_order_not_found(self):
        conn = self._open_migrated()
        self._seed_work_order(conn)
        with self.assertRaises(NotFoundError):
            self._transition(conn, {"id": "wor-missing"}, "assigned", 1)
