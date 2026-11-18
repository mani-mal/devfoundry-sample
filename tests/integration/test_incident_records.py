"""Integration tests (T053): incident records and linked work orders.

Uses the REAL shipped migrations against a temporary file database (no
CREATE TABLE) and drives the incident module through its public
functions only, with a _tick_clock helper giving every call a FRESH
DISTINCT clock instant (UTC, RFC3339 Z, second precision; no fixed
timestamps anywhere in this file).
"""

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from opsledger.core import OrganizationContext
from opsledger.assets import create_asset, create_site
from opsledger.core.clock import FixedClock, format_rfc3339
from opsledger.core.db import connect
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError
from opsledger.core.migrations import migrate
from opsledger.incidents.records import (
    DUPLICATE_LINK_MESSAGE,
    INCIDENT_NOT_FOUND_MESSAGE,
    SITE_MISMATCH_MESSAGE,
    create_incident,
    get_incident,
    list_incidents,
    list_linked_work_orders,
    link_work_order,
)
from opsledger.workorders import create_work_order


class IncidentRecordTest(unittest.TestCase):
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
        created_text = format_rfc3339(datetime.now(timezone.utc))
        with conn:
            conn.execute(
                "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                (organization_id, organization_id, "Organization", created_text),
            )

    def _seed_users(self, conn):
        created_text = format_rfc3339(datetime.now(timezone.utc))
        with conn:
            conn.execute(
                "INSERT INTO users (id, email, display_name, created_at) VALUES (?, ?, ?, ?)",
                ("user-111", "user-111@example.com", "Requester One", created_text),
            )
            conn.execute(
                "INSERT INTO users (id, email, display_name, created_at) VALUES (?, ?, ?, ?)",
                ("user-999", "user-999@example.com", "Second User", created_text),
            )

    def _seed_membership(self, conn, user_id, role, organization_id="org-aaa"):
        created_text = format_rfc3339(datetime.now(timezone.utc))
        with conn:
            conn.execute(
                "INSERT INTO memberships (organization_id, user_id, role, created_at)"
                " VALUES (?, ?, ?, ?)",
                (organization_id, user_id, role, created_text),
            )

    def _context(self, organization_id="org-aaa", actor_id="user-111"):
        return OrganizationContext(organization_id=organization_id, actor_id=actor_id)

    def _tick_clock(self):
        """Each call returns a FRESH DISTINCT clock: UTC, RFC3339 Z, seconds."""
        self._clock_tick += 1
        return FixedClock(datetime.now(timezone.utc) + timedelta(seconds=self._clock_tick))

    def _site(self, conn, context, code):
        return create_site(conn, context, code=code, name="Site", clock=self._tick_clock())

    def _asset(self, conn, context, site_id, tag):
        return create_asset(
            conn, context, site_id=site_id, tag=tag, name="Asset",
            criticality="low", purchase_cost_cents=1000, clock=self._tick_clock(),
        )

    def _work_order(self, conn, context, site_id, asset_id, number):
        return create_work_order(
            conn, context, site_id=site_id, asset_id=asset_id, number=number,
            title="Work order", description="Work", priority="low",
            requester_id=context.actor_id, clock=self._tick_clock(),
        )

    def _incident(self, conn, context, *, site_id, asset_id=None, title="Incident"):
        return create_incident(
            conn, context, site_id=site_id, asset_id=asset_id,
            reported_by=context.actor_id, title=title, description="Incident",
            severity="low", occurred_at=None, clock=self._tick_clock(),
        )

    def test_t1_create_incident_returns_open_row_and_get_returns_it(self):
        conn = self._open_migrated()
        self._seed_organization(conn)
        self._seed_users(conn)
        self._seed_membership(conn, "user-111", "developer")
        context = self._context()
        site = self._site(conn, context, "site-1")
        incident = self._incident(conn, context, site_id=site["id"])
        self.assertEqual("open", incident["status"])
        self.assertEqual(1, incident["version"])
        self.assertIsNone(incident["closed_at"])
        fetched = get_incident(conn, context, incident_id=incident["id"])
        self.assertEqual(incident["id"], fetched["id"])
        self.assertEqual("open", fetched["status"])
        self.assertEqual(1, fetched["version"])
        self.assertIsNone(fetched["closed_at"])

    def test_t2_create_refuses_invalid_severity_and_malformed_occurred_at(self):
        conn = self._open_migrated()
        self._seed_organization(conn)
        self._seed_users(conn)
        self._seed_membership(conn, "user-111", "developer")
        context = self._context()
        site = self._site(conn, context, "site-2")
        with self.assertRaises(ValidationError):
            create_incident(
                conn, context, site_id=site["id"], asset_id=None,
                reported_by=context.actor_id, title="Incident",
                description="Incident", severity="urgent", occurred_at=None,
                clock=self._tick_clock(),
            )
        with self.assertRaises(ValidationError):
            create_incident(
                conn, context, site_id=site["id"], asset_id=None,
                reported_by=context.actor_id, title="Incident",
                description="Incident", severity="low",
                occurred_at="not-a-date", clock=self._tick_clock(),
            )
        self.assertEqual(0, conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0])

    def test_t2b_create_refuses_201_char_title_and_accepts_200_char_title(self):
        conn = self._open_migrated()
        self._seed_organization(conn)
        self._seed_users(conn)
        self._seed_membership(conn, "user-111", "developer")
        context = self._context()
        site = self._site(conn, context, "site-1")
        with self.assertRaises(ValidationError) as caught:
            self._incident(conn, context, site_id=site["id"], title="x" * 201)
        self.assertEqual("title must be at most 200 characters", str(caught.exception))
        long_ok = self._incident(conn, context, site_id=site["id"], title="y" * 200)
        self.assertEqual(200, len(long_ok["title"]))
        self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0])

    def test_t2c_create_refuses_none_title_as_validation_error(self):
        conn = self._open_migrated()
        self._seed_organization(conn)
        self._seed_users(conn)
        self._seed_membership(conn, "user-111", "developer")
        context = self._context()
        site = self._site(conn, context, "site-1")
        with self.assertRaises(ValidationError):
            create_incident(
                conn, context, site_id=site["id"], asset_id=None,
                reported_by=context.actor_id, title=None, description="Incident",
                severity="low", occurred_at=None, clock=self._tick_clock(),
            )
        self.assertEqual(0, conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0])

    def test_t2d_occurred_at_accepted_and_stored_verbatim(self):
        conn = self._open_migrated()
        self._seed_organization(conn)
        self._seed_users(conn)
        self._seed_membership(conn, "user-111", "developer")
        context = self._context()
        site = self._site(conn, context, "site-1")
        occurred_text = "2026-11-16T12:00:00Z"
        incident = create_incident(
            conn, context, site_id=site["id"], asset_id=None,
            reported_by=context.actor_id, title="Incident",
            description="Incident", severity="low", occurred_at=occurred_text,
            clock=self._tick_clock(),
        )
        self.assertEqual(occurred_text, incident["occurred_at"])
        fetched = get_incident(conn, context, incident_id=incident["id"])
        self.assertEqual(occurred_text, fetched["occurred_at"])

    def test_t3_create_refuses_archived_site_and_archived_asset(self):
        conn = self._open_migrated()
        self._seed_organization(conn)
        self._seed_users(conn)
        self._seed_membership(conn, "user-111", "developer")
        context = self._context()
        site = self._site(conn, context, "site-1")
        asset = self._asset(conn, context, site["id"], "tag-1")
        archived_site_row = conn.execute(
            "UPDATE sites SET archived_at = ? WHERE id = ?",
            (format_rfc3339(datetime.now(timezone.utc)), site["id"]),
        )
        self.assertEqual(1, archived_site_row.rowcount)
        with self.assertRaises(ValidationError):
            create_incident(
                conn, context, site_id=site["id"], asset_id=None,
                reported_by=context.actor_id, title="Incident",
                description="Incident", severity="low", occurred_at=None,
                clock=self._tick_clock(),
            )
        conn.execute(
            "UPDATE sites SET archived_at = NULL WHERE id = ?", (site["id"],)
        )
        conn.execute(
            "UPDATE assets SET archived_at = ? WHERE id = ?",
            (format_rfc3339(datetime.now(timezone.utc)), asset["id"]),
        )
        with self.assertRaises(ValidationError):
            create_incident(
                conn, context, site_id=site["id"], asset_id=asset["id"],
                reported_by=context.actor_id, title="Incident",
                description="Incident", severity="low", occurred_at=None,
                clock=self._tick_clock(),
            )
        self.assertEqual(0, conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0])

    def test_t4_create_accepts_no_asset(self):
        conn = self._open_migrated()
        self._seed_organization(conn)
        self._seed_users(conn)
        self._seed_membership(conn, "user-111", "developer")
        context = self._context()
        site = self._site(conn, context, "site-1")
        incident = self._incident(conn, context, site_id=site["id"], asset_id=None)
        self.assertIsNone(incident["asset_id"])
        self.assertEqual("open", incident["status"])

    def test_t5_link_work_order_links_same_site_order_and_lists_it(self):
        conn = self._open_migrated()
        self._seed_organization(conn)
        self._seed_users(conn)
        self._seed_membership(conn, "user-111", "developer")
        context = self._context()
        site = self._site(conn, context, "site-1")
        asset = self._asset(conn, context, site["id"], "tag-1")
        incident = self._incident(conn, context, site_id=site["id"])
        work_order = self._work_order(conn, context, site["id"], asset["id"], "wo-1")
        link = link_work_order(
            conn, context, incident_id=incident["id"],
            work_order_id=work_order["id"], clock=self._tick_clock(),
        )
        self.assertIsNotNone(link["id"])
        self.assertEqual(incident["id"], link["incident_id"])
        self.assertEqual(work_order["id"], link["work_order_id"])
        linked = list_linked_work_orders(conn, context, incident_id=incident["id"])
        self.assertEqual(1, len(linked))
        self.assertEqual(work_order["id"], linked[0]["id"])

    def test_t6_link_refuses_cross_site_work_order_and_duplicate_link(self):
        conn = self._open_migrated()
        self._seed_organization(conn)
        self._seed_users(conn)
        self._seed_membership(conn, "user-111", "developer")
        context = self._context()
        site_a = self._site(conn, context, "site-a")
        site_b = self._site(conn, context, "site-b")
        asset_a = self._asset(conn, context, site_a["id"], "tag-a")
        asset_b = self._asset(conn, context, site_b["id"], "tag-b")
        incident = self._incident(conn, context, site_id=site_a["id"])
        work_order_b = self._work_order(conn, context, site_b["id"], asset_b["id"], "wo-b")
        work_order_a = self._work_order(conn, context, site_a["id"], asset_a["id"], "wo-a")
        with self.assertRaises(ValidationError) as caught:
            link_work_order(
                conn, context, incident_id=incident["id"],
                work_order_id=work_order_b["id"], clock=self._tick_clock(),
            )
        self.assertEqual(SITE_MISMATCH_MESSAGE, str(caught.exception))
        link = link_work_order(
            conn, context, incident_id=incident["id"],
            work_order_id=work_order_a["id"], clock=self._tick_clock(),
        )
        self.assertIsNotNone(link["id"])
        with self.assertRaises(ConflictError) as caught_dup:
            link_work_order(
                conn, context, incident_id=incident["id"],
                work_order_id=work_order_a["id"], clock=self._tick_clock(),
            )
        self.assertEqual(DUPLICATE_LINK_MESSAGE, str(caught_dup.exception))

    def test_t7_list_incidents_is_org_scoped_and_filters_by_status(self):
        conn = self._open_migrated()
        self._seed_organization(conn, "org-aaa")
        self._seed_organization(conn, "org-bbb")
        self._seed_users(conn)
        self._seed_membership(conn, "user-111", "developer", "org-aaa")
        context_a = self._context("org-aaa")
        context_b = self._context("org-bbb")
        site = self._site(conn, context_a, "site-1")
        incident = self._incident(conn, context_a, site_id=site["id"])
        self.assertEqual([], list_incidents(conn, context_b))
        self.assertEqual(1, len(list_incidents(conn, context_a)))
        self.assertEqual(1, len(list_incidents(conn, context_a, status="open")))
        self.assertEqual([], list_incidents(conn, context_a, status="closed"))

    def test_t8_get_incident_not_found_for_missing_and_cross_org_ids(self):
        conn = self._open_migrated()
        self._seed_organization(conn, "org-aaa")
        self._seed_organization(conn, "org-bbb")
        self._seed_users(conn)
        self._seed_membership(conn, "user-111", "developer", "org-aaa")
        context_a = self._context("org-aaa")
        context_b = self._context("org-bbb")
        site = self._site(conn, context_a, "site-1")
        incident = self._incident(conn, context_a, site_id=site["id"])
        with self.assertRaises(NotFoundError) as caught_missing:
            get_incident(conn, context_b, incident_id="wor-no-such-id")
        self.assertEqual(INCIDENT_NOT_FOUND_MESSAGE, str(caught_missing.exception))
        with self.assertRaises(NotFoundError) as caught_cross:
            get_incident(conn, context_b, incident_id=incident["id"])
        self.assertEqual(INCIDENT_NOT_FOUND_MESSAGE, str(caught_cross.exception))
        self.assertEqual(
            str(caught_missing.exception), str(caught_cross.exception)
        )


if __name__ == "__main__":
    unittest.main()
