"""Integration tests (T043): line-edit service for purchase requests.

Uses the REAL shipped migrations against a temporary file database (no
CREATE TABLE) and drives the line-edit service through its public
functions only, with a _tick_clock helper giving every call a FRESH
DISTINCT clock instant (UTC, RFC3339 Z, second precision; no fixed
timestamps anywhere in this file).
"""

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock, format_rfc3339
from opsledger.core.db import connect
from opsledger.core.errors import ConflictError, NotFoundError
from opsledger.core.migrations import migrate
from opsledger.parts import create_part
from opsledger.purchasing.line_edits import add_request_line, update_request_line
from opsledger.purchasing.lifecycle import approve_purchase_request, submit_purchase_request
from opsledger.purchasing.requests import create_purchase_request
from opsledger.purchasing.vendors import create_vendor


class PurchaseRequestLineEditsTest(unittest.TestCase):
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

    def _seed_organizations(self, conn, *, extra_org=False):
        created_text = format_rfc3339(datetime.now(timezone.utc))
        with conn:
            conn.execute(
                "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                ("org-aaa", "org-aaa", "Organization AAA", created_text),
            )
            if extra_org:
                conn.execute(
                    "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                    ("org-bbb", "org-bbb", "Organization BBB", created_text),
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
                ("user-999", "user-999@example.com", "Approver Nine", created_text),
            )

    def _seed_membership(self, conn, user_id, role):
        created_text = format_rfc3339(datetime.now(timezone.utc))
        with conn:
            conn.execute(
                "INSERT INTO memberships (organization_id, user_id, role, created_at)"
                " VALUES (?, ?, ?, ?)",
                ("org-aaa", user_id, role, created_text),
            )

    def _context(self, organization_id="org-aaa", actor_id="user-111"):
        return OrganizationContext(organization_id=organization_id, actor_id=actor_id)

    def _tick_clock(self):
        """Each call returns a FRESH DISTINCT clock: UTC, RFC3339 Z, seconds; no fixed timestamps."""
        self._clock_tick += 1
        return FixedClock(datetime.now(timezone.utc) + timedelta(seconds=self._clock_tick))

    def _vendor(self, conn, context, name="Acme"):
        return create_vendor(conn, context, name=name, contact_email=None, clock=self._tick_clock())

    def _part(self, conn, context, sku, name):
        return create_part(
            conn, context, sku=sku, name=name,
            unit_of_measure="unit", standard_cost_cents=2500,
            clock=self._tick_clock(),
        )

    def _request(self, conn, context, vendor_id, lines):
        return create_purchase_request(
            conn, context, vendor_id=vendor_id, lines=lines, clock=self._tick_clock(),
        )

    def _line_id(self, db_path, request_id):
        """Return the id of the request's single live line (fresh connection)."""
        conn = connect(db_path)
        try:
            return conn.execute(
                "SELECT id FROM purchase_request_lines"
                " WHERE purchase_request_id = ? AND archived_at IS NULL"
                " ORDER BY created_at, id LIMIT 1",
                (request_id,),
            ).fetchone()[0]
        finally:
            conn.close()

    def _request_row(self, db_path, request_id):
        """Select one purchase request row through a fresh connection."""
        conn = connect(db_path)
        try:
            return conn.execute(
                "SELECT * FROM purchase_requests WHERE id = ?", (request_id,)
            ).fetchone()
        finally:
            conn.close()

    def _approval_rows(self, db_path):
        """Select all approval rows through a fresh connection."""
        conn = connect(db_path)
        try:
            return conn.execute("SELECT * FROM approvals").fetchall()
        finally:
            conn.close()

    def _audit_count(self, db_path):
        """Count audit rows through a fresh connection."""
        conn = connect(db_path)
        try:
            return conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
        finally:
            conn.close()

    def test_t1_update_line_refused_on_approved_request(self):
        conn = self._open_migrated()
        db_path = conn.execute("PRAGMA database_list").fetchone()[2]
        self._seed_organizations(conn)
        self._seed_users(conn)
        self._seed_membership(conn, "user-999", "approver")
        requester = self._context(actor_id="user-111")
        approver = self._context(actor_id="user-999")
        vendor = self._vendor(conn, requester)
        bolt = self._part(conn, requester, sku="bolt-m8", name="M8 bolt")
        lines = [{"part_id": bolt["id"], "quantity": 4, "unit_cost_cents": 2500}]
        request = self._request(conn, requester, vendor["id"], lines)
        self.assertEqual(10000, request["total_cents"])
        submitted = submit_purchase_request(
            conn, requester,
            purchase_request_id=request["id"], expected_version=1,
            clock=self._tick_clock(),
        )
        self.assertEqual("submitted", submitted["status"])
        approved = approve_purchase_request(
            conn, approver,
            purchase_request_id=request["id"], expected_version=2,
            clock=self._tick_clock(),
        )
        self.assertEqual("approved", approved["status"])
        line_id = self._line_id(db_path, request["id"])
        with self.assertRaises(ConflictError) as caught:
            update_request_line(
                conn, requester,
                purchase_request_line_id=line_id,
                quantity=5, unit_cost_cents=2500, expected_version=3,
                clock=self._tick_clock(),
            )
        self.assertIn("cannot be edited", str(caught.exception))
        row = self._request_row(db_path, request["id"])
        self.assertEqual("approved", row["status"])
        self.assertEqual(10000, row["total_cents"])
        approvals = self._approval_rows(db_path)
        self.assertEqual(1, len(approvals))
        self.assertIsNone(approvals[0]["invalidated_at"])

    def test_t2_update_line_accepted_on_submitted_request_with_live_approval(self):
        conn = self._open_migrated()
        db_path = conn.execute("PRAGMA database_list").fetchone()[2]
        self._seed_organizations(conn)
        self._seed_users(conn)
        requester = self._context(actor_id="user-111")
        vendor = self._vendor(conn, requester)
        bolt = self._part(conn, requester, sku="bolt-m8", name="M8 bolt")
        lines = [{"part_id": bolt["id"], "quantity": 4, "unit_cost_cents": 2500}]
        request = self._request(conn, requester, vendor["id"], lines)
        self.assertEqual(10000, request["total_cents"])
        now_text = format_rfc3339(datetime.now(timezone.utc))
        with conn:
            conn.execute("UPDATE purchase_requests SET status = 'submitted' WHERE id = ?", (request["id"],))
            conn.execute(
                "INSERT INTO approvals (id, organization_id, purchase_request_id,"
                " approver_id, decision, approved_total_cents, reason, decided_at,"
                " created_at, updated_at, invalidated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    "apr-seed-0001",
                    "org-aaa",
                    request["id"],
                    "user-999",
                    "approved",
                    10000,
                    None,
                    now_text,
                    now_text,
                    now_text,
                ),
            )
        line_id = self._line_id(db_path, request["id"])
        updated = update_request_line(
            conn, requester,
            purchase_request_line_id=line_id,
            quantity=5, unit_cost_cents=2500, expected_version=1,
            clock=self._tick_clock(),
        )
        self.assertEqual("draft", updated["status"])
        self.assertEqual(12500, updated["total_cents"])
        approvals = self._approval_rows(db_path)
        self.assertEqual(1, len(approvals))
        self.assertIsNotNone(approvals[0]["invalidated_at"])
        row = self._request_row(db_path, request["id"])
        self.assertEqual("draft", row["status"])
        self.assertEqual(12500, row["total_cents"])

    def test_t3_add_line_on_submitted_request_reverts_to_draft(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        self._seed_users(conn)
        requester = self._context(actor_id="user-111")
        vendor = self._vendor(conn, requester)
        bolt = self._part(conn, requester, sku="bolt-m8", name="M8 bolt")
        lines = [{"part_id": bolt["id"], "quantity": 4, "unit_cost_cents": 2500}]
        request = self._request(conn, requester, vendor["id"], lines)
        self.assertEqual(10000, request["total_cents"])
        with conn:
            conn.execute("UPDATE purchase_requests SET status = 'submitted' WHERE id = ?", (request["id"],))
        washer = self._part(conn, requester, sku="washer-m8", name="M8 washer")
        updated = add_request_line(
            conn, requester,
            purchase_request_id=request["id"],
            part_id=washer["id"],
            quantity=2, unit_cost_cents=1000, expected_version=1,
            clock=self._tick_clock(),
        )
        self.assertEqual("draft", updated["status"])
        self.assertEqual(12000, updated["total_cents"])

    def test_t4_unknown_line_id_raises_canonical_not_found(self):
        conn = self._open_migrated()
        db_path = conn.execute("PRAGMA database_list").fetchone()[2]
        self._seed_organizations(conn)
        self._seed_users(conn)
        requester = self._context(actor_id="user-111")
        vendor = self._vendor(conn, requester)
        bolt = self._part(conn, requester, sku="bolt-m8", name="M8 bolt")
        lines = [{"part_id": bolt["id"], "quantity": 4, "unit_cost_cents": 2500}]
        request = self._request(conn, requester, vendor["id"], lines)
        self.assertEqual(10000, request["total_cents"])
        audit_before = self._audit_count(db_path)
        with self.assertRaises(NotFoundError) as caught:
            update_request_line(
                conn, requester,
                purchase_request_line_id="prl-00000000000000000000000000000000",
                quantity=5, unit_cost_cents=2500, expected_version=1,
                clock=self._tick_clock(),
            )
        self.assertIn("purchase request line not found", str(caught.exception))
        audit_after = self._audit_count(db_path)
        self.assertEqual(audit_before, audit_after)
        row = self._request_row(db_path, request["id"])
        self.assertEqual("draft", row["status"])
        self.assertEqual(10000, row["total_cents"])
        self.assertEqual(0, len(self._approval_rows(db_path)))

    def test_t5_cross_org_line_id_raises_canonical_not_found(self):
        conn = self._open_migrated()
        db_path = conn.execute("PRAGMA database_list").fetchone()[2]
        self._seed_organizations(conn, extra_org=True)
        self._seed_users(conn)
        requester = self._context(actor_id="user-111")
        other_org = self._context(organization_id="org-bbb", actor_id="user-111")
        vendor = self._vendor(conn, requester)
        bolt = self._part(conn, requester, sku="bolt-m8", name="M8 bolt")
        lines = [{"part_id": bolt["id"], "quantity": 4, "unit_cost_cents": 2500}]
        request = self._request(conn, requester, vendor["id"], lines)
        self.assertEqual(10000, request["total_cents"])
        line_id = self._line_id(db_path, request["id"])
        audit_before = self._audit_count(db_path)
        with self.assertRaises(NotFoundError) as raised:
            update_request_line(
                conn, other_org,
                purchase_request_line_id=line_id,
                quantity=5, unit_cost_cents=2500, expected_version=1,
                clock=self._tick_clock(),
            )
        self.assertIn("purchase request line not found", str(raised.exception))
        audit_after = self._audit_count(db_path)
        self.assertEqual(audit_before, audit_after)
        row = self._request_row(db_path, request["id"])
        self.assertEqual("draft", row["status"])
        self.assertEqual(10000, row["total_cents"])
        self.assertEqual(0, len(self._approval_rows(db_path)))

    def test_t6_stale_expected_version_conflict_on_update(self):
        conn = self._open_migrated()
        db_path = conn.execute("PRAGMA database_list").fetchone()[2]
        self._seed_organizations(conn)
        self._seed_users(conn)
        requester = self._context(actor_id="user-111")
        vendor = self._vendor(conn, requester)
        bolt = self._part(conn, requester, sku="bolt-m8", name="M8 bolt")
        lines = [{"part_id": bolt["id"], "quantity": 4, "unit_cost_cents": 2500}]
        request = self._request(conn, requester, vendor["id"], lines)
        self.assertEqual(10000, request["total_cents"])
        line_id = self._line_id(db_path, request["id"])
        audit_before = self._audit_count(db_path)
        with self.assertRaises(ConflictError) as caught:
            update_request_line(
                conn, requester,
                purchase_request_line_id=line_id,
                quantity=5, unit_cost_cents=2500, expected_version=99,
                clock=self._tick_clock(),
            )
        self.assertIn("version conflict", str(caught.exception))
        audit_after = self._audit_count(db_path)
        self.assertEqual(audit_before, audit_after)
        row = self._request_row(db_path, request["id"])
        self.assertEqual("draft", row["status"])
        self.assertEqual(10000, row["total_cents"])
        self.assertEqual(1, row["version"])
        self.assertEqual(0, len(self._approval_rows(db_path)))


if __name__ == "__main__":
    unittest.main()
