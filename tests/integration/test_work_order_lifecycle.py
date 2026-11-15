"""Black-box regression (T032, M4): work-order lifecycle + audit history.

Applies the REAL shipped migrations to a temporary file database and
exercises the full work-order lifecycle through the PUBLIC service
functions only — no direct table writes to business tables anywhere in
the test. Acceptance (spec M4/T032): open-to-close and reopen preserve
correct history; every transition leaves one work_order_events row and
one audit_events row, in order, and audit details carry from/to status
and from/to version.
"""

import json
import tempfile
import unittest
from datetime import datetime, timezone

from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect
from opsledger.core.errors import ConflictError
from opsledger.core.migrations import migrate
from opsledger.assets import create_asset, create_site
from opsledger.workorders import create_work_order
from opsledger.workorders.transitions import transition_work_order
from opsledger.audit import events_for_entity

AUDIT_ENTITY_WORK_ORDER = "work_order"


class WorkOrderLifecycleRegression(unittest.TestCase):
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
        # Distinct timestamp per transition: created_at ties are broken by
        # the random event id, so tests advance the clock per call to keep
        # ORDER BY created_at, id deterministic.
        self._tick = getattr(self, "_tick", 0) + 1
        return transition_work_order(
            conn, self._context(), work_order_id=work_order["id"], to_status=to_status,
            expected_version=expected_version, reason=reason, actor_id="user-111",
            clock=FixedClock(datetime(2026, 11, 13, 15, self._tick, 0, tzinfo=timezone.utc)),
        )

    def _lifecycle_events(self, conn, work_order_id):
        return conn.execute(
            "SELECT * FROM work_order_events WHERE work_order_id = ?"
            " ORDER BY created_at, id",
            (work_order_id,),
        ).fetchall()

    def _audit_events(self, conn, work_order_id):
        return events_for_entity(
            conn, self._context(), entity_type=AUDIT_ENTITY_WORK_ORDER, entity_id=work_order_id,
        )

    def test_t1_full_open_to_close_walk_preserves_history(self):
        conn = self._open_migrated()
        _, _, work_order = self._seed_work_order(conn)
        row = self._transition(conn, work_order, "assigned", 1)
        row = self._transition(conn, row, "in_progress", 2)
        row = self._transition(conn, row, "completed", 3)
        row = self._transition(conn, row, "closed", 4)
        self.assertEqual("closed", row["status"])
        self.assertEqual(5, row["version"])
        events = self._lifecycle_events(conn, work_order["id"])
        self.assertEqual(
            [("open", "assigned"), ("assigned", "in_progress"),
             ("in_progress", "completed"), ("completed", "closed")],
            [(event["from_status"], event["to_status"]) for event in events],
        )
        self.assertEqual(4, len(events))
        audit = self._audit_events(conn, work_order["id"])
        self.assertEqual(4, len(audit))
        self.assertEqual(
            ["work_order.transition"] * 4,
            [event["operation"] for event in audit],
        )

    def test_t2_reopen_from_closed_returns_to_open_with_history_intact(self):
        conn = self._open_migrated()
        _, _, work_order = self._seed_work_order(conn)
        row = self._transition(conn, work_order, "assigned", 1)
        row = self._transition(conn, row, "in_progress", 2)
        row = self._transition(conn, row, "completed", 3)
        row = self._transition(conn, row, "closed", 4)
        row = self._transition(conn, row, "open", 5, reason="reopen")
        self.assertEqual("open", row["status"])
        self.assertEqual(6, row["version"])
        events = self._lifecycle_events(conn, work_order["id"])
        self.assertEqual(5, len(events))
        self.assertEqual(("closed", "open"), (events[-1]["from_status"], events[-1]["to_status"]))
        self.assertEqual("reopen", events[-1]["reason"])
        audit = self._audit_events(conn, work_order["id"])
        self.assertEqual(5, len(audit))
        details = json.loads(audit[-1]["details"])
        self.assertEqual(
            {"from_status": "closed", "to_status": "open", "from_version": 5, "to_version": 6},
            {key: details[key] for key in ("from_status", "to_status", "from_version", "to_version")},
        )
