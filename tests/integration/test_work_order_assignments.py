"""Integration tests (T026b): work-order assignment service.

These tests apply the REAL shipped migrations to a temporary file database
and then exercise :func:`opsledger.workorders.assignments.assign_technician`
and :func:`opsledger.workorders.assignments.release_assignment` against that
migrated schema — no CREATE TABLE anywhere in the test. Acceptance (spec
M4/T026): assignment requires an active technician in the same site;
cross-site and inactive assignees are denied; one active assignment per
work order; release keeps the history.
"""

import tempfile
import unittest
from datetime import datetime, timezone

from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect
from opsledger.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from opsledger.core.migrations import migrate
from opsledger.assets import create_asset, create_site
from opsledger.workorders import create_work_order
from opsledger.workorders.assignments import (
    ACTIVE_ASSIGNMENT_EXISTS_MESSAGE,
    ASSIGNEE_NOT_ACTIVE_TECHNICIAN_MESSAGE,
    WORK_ORDER_NOT_OPEN_MESSAGE,
    assign_technician,
    release_assignment,
)


class AssignmentTests(unittest.TestCase):
    """Integration tests for assign_technician on the real migrated schema."""

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

    def _clock(self):
        return FixedClock(datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc))

    def _seed(self, conn):
        clock = self._clock()
        self._seed_organizations(conn)
        site_a = create_site(conn, self._context("org-aaa"), code="main", name="Site A", clock=clock)
        site_b = create_site(conn, self._context("org-bbb"), code="main", name="Site B", clock=clock)
        site_west = create_site(conn, self._context("org-aaa"), code="west", name="Site West", clock=clock)
        asset_a = create_asset(
            conn, self._context("org-aaa"), site_id=site_a["id"], tag="pump-001",
            name="Asset pump-001", criticality="medium", purchase_cost_cents=10000, clock=clock,
        )
        work_order = create_work_order(
            conn, self._context("org-aaa"), site_id=site_a["id"], asset_id=asset_a["id"],
            number="wo-100", title="Rebuild pump", description="Full rebuild",
            priority="high", requester_id="user-111", clock=clock,
        )
        return site_a, site_b, site_west, asset_a, work_order

    def _grant(self, conn, site_id, user_id, organization_id="org-aaa", revoked=False):
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (id, email, display_name, created_at) VALUES (?, ?, ?, ?)",
                (user_id, user_id + "@example.test", "User " + user_id, "2026-11-13T11:00:00Z"),
            )
            conn.execute(
                "INSERT INTO site_memberships (organization_id, site_id, user_id, granted_at, revoked_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (organization_id, site_id, user_id, "2026-11-13T12:00:00Z",
                 "2026-11-13T13:00:00Z" if revoked else None),
            )

    def _assign(self, conn, work_order, technician_id, organization_id="org-aaa"):
        return assign_technician(
            conn, self._context(organization_id), work_order_id=work_order["id"],
            technician_id=technician_id, assigned_by_id="user-222",
            clock=FixedClock(datetime(2026, 11, 13, 15, 0, 0, tzinfo=timezone.utc)),
        )
