"""Integration tests (T054): corrective actions and incident closure.

REAL shipped migrations on a temporary file database (no CREATE TABLE),
driven through the public functions only; each _tick_clock call returns
a FRESH DISTINCT clock instant (UTC, RFC3339 Z, second precision; no
fixed timestamps anywhere in this file).
"""
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from opsledger.assets import create_asset, create_site
from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect
from opsledger.core.errors import ConflictError, ValidationError
from opsledger.core.migrations import migrate
from opsledger.incidents.actions import (
    OPEN_REQUIRED_ACTION_MESSAGE,
    add_corrective_action,
    assign_corrective_action,
    close_incident,
    complete_corrective_action,
    list_corrective_actions,
)
from opsledger.incidents.records import create_incident


class IncidentActionTest(unittest.TestCase):
    def setUp(self):
        self._clock_tick = 0

    def _open_migrated(self):
        """Open a temporary file database with the REAL shipped migrations (no CREATE TABLE)."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda p=tmp.name: os.path.exists(p) and os.unlink(p))
        self.addCleanup(lambda: connect(tmp.name).close())
        conn = connect(tmp.name)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def _seed_organization(self, conn, organization_id="org-aaa"):
        created_text = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with conn:
            conn.execute("INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)", (organization_id, organization_id, "Organization", created_text))

    def _seed_users(self, conn):
        created_text = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with conn:
            conn.execute("INSERT INTO users (id, email, display_name, created_at) VALUES (?, ?, ?, ?)", ("user-111", "user-111@example.com", "Requester One", created_text))
            conn.execute("INSERT INTO users (id, email, display_name, created_at) VALUES (?, ?, ?, ?)", ("user-999", "user-999@example.com", "Second User", created_text))

    def _context(self, organization_id="org-aaa", actor_id="user-111"):
        return OrganizationContext(organization_id=organization_id, actor_id=actor_id)

    def _tick_clock(self):
        """Each call returns a FRESH DISTINCT clock: UTC, RFC3339 Z, seconds."""
        self._clock_tick += 1
        return FixedClock(datetime.now(timezone.utc) + timedelta(seconds=self._clock_tick))

    def _seed_incident(self, conn, context, site_code="site-1", asset_tag="tag-1"):
        """Create one owned site/asset/incident through the public services."""
        site = create_site(conn, context, code=site_code, name="Site", clock=self._tick_clock())
        asset = create_asset(conn, context, site_id=site["id"], tag=asset_tag, name="Asset", criticality="low", purchase_cost_cents=1000, clock=self._tick_clock())
        return create_incident(conn, context, site_id=site["id"], asset_id=asset["id"], reported_by=context.actor_id, title="Incident", description="Incident", severity="low", occurred_at=None, clock=self._tick_clock())

    def test_t1_add_assign_complete_a_corrective_action(self):
        conn = self._open_migrated()
        self._seed_organization(conn)
        self._seed_users(conn)
        context = self._context()
        incident = self._seed_incident(conn, context)
        action = add_corrective_action(conn, context, incident_id=incident["id"], title="Patch asset", instructions="Apply the vendor patch", required=True, clock=self._tick_clock())
        self.assertEqual("open", action["status"])
        self.assertIsNone(action["assigned_to"])
        assigned = assign_corrective_action(conn, context, action_id=action["id"], assignee_id="user-999", clock=self._tick_clock())
        self.assertEqual("user-999", assigned["assigned_to"])
        self.assertEqual("in_progress", assigned["status"])
        with self.assertRaises(ValidationError):
            assign_corrective_action(conn, context, action_id=action["id"], assignee_id="user-no-such", clock=self._tick_clock())
        done = complete_corrective_action(conn, context, action_id=action["id"], clock=self._tick_clock())
        self.assertEqual("done", done["status"])
        self.assertIsNotNone(done["completed_at"])
        with self.assertRaises(ConflictError) as caught_twice:
            complete_corrective_action(conn, context, action_id=action["id"], clock=self._tick_clock())
        self.assertIn("already done", str(caught_twice.exception))

    def test_t2_closure_blocked_by_open_required_action_then_succeeds(self):
        conn = self._open_migrated()
        self._seed_organization(conn)
        self._seed_users(conn)
        context = self._context()
        incident = self._seed_incident(conn, context)
        required = add_corrective_action(conn, context, incident_id=incident["id"], title="Patch asset", instructions="Apply the vendor patch", required=True, clock=self._tick_clock())
        optional = add_corrective_action(conn, context, incident_id=incident["id"], title="Note follow-up", instructions="Log the follow-up note", required=False, clock=self._tick_clock())
        with self.assertRaises(ConflictError) as blocked:
            close_incident(conn, context, incident_id=incident["id"], expected_version=incident["version"], clock=self._tick_clock())
        self.assertEqual(OPEN_REQUIRED_ACTION_MESSAGE, str(blocked.exception))
        self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM incidents WHERE status = 'open' AND closed_at IS NULL").fetchone()[0])
        complete_corrective_action(conn, context, action_id=required["id"], clock=self._tick_clock())
        self.assertEqual(0, conn.execute("SELECT COUNT(*) FROM incidents WHERE status = 'closed'").fetchone()[0])
        closed = close_incident(conn, context, incident_id=incident["id"], expected_version=incident["version"], clock=self._tick_clock())
        self.assertEqual("closed", closed["status"])
        self.assertIsNotNone(closed["closed_at"])
        self.assertEqual(incident["version"] + 1, closed["version"])
        self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM corrective_actions WHERE id = ? AND status = 'open'", (optional["id"],)).fetchone()[0])
        ordered = list_corrective_actions(conn, context, incident_id=incident["id"])
        self.assertEqual([required["id"], optional["id"]], [row["id"] for row in ordered])
