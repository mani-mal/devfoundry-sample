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
