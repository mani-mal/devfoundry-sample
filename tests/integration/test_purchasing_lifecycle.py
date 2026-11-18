"""Integration tests (T042): purchase-request lifecycle.

Uses the REAL shipped migrations against a temporary file database (no
CREATE TABLE) and drives the lifecycle service through its public
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
from opsledger.core.errors import ConflictError, PermissionDeniedError, ValidationError
from opsledger.core.migrations import migrate
from opsledger.parts import create_part
from opsledger.purchasing.lifecycle import (
    approve_purchase_request,
    cancel_purchase_request,
    reject_purchase_request,
    submit_purchase_request,
)
from opsledger.purchasing.requests import create_purchase_request
from opsledger.purchasing.vendors import create_vendor


class PurchaseRequestLifecycleTest(unittest.TestCase):
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

    def _seed_organizations(self, conn):
        created_text = format_rfc3339(datetime.now(timezone.utc))
        with conn:
            conn.execute(
                "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                ("org-aaa", "org-aaa", "Organization AAA", created_text),
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
            conn.execute(
                "INSERT INTO users (id, email, display_name, created_at) VALUES (?, ?, ?, ?)",
                ("user-777", "user-777@example.com", "Outsider Seven", created_text),
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

    def _approvals(self, conn):
        return conn.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]

    def test_t1_submit_then_approve_flow_records_exactly_one_approval_row(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        self._seed_users(conn)
        self._seed_membership(conn, "user-999", "approver")
        requester = self._context(actor_id="user-111")
        approver = self._context(actor_id="user-999")
        vendor = self._vendor(conn, requester)
        bolt = self._part(conn, requester, sku="bolt-m8", name="M8 bolt")
        lines = [{"part_id": bolt["id"], "quantity": 4, "unit_cost_cents": 2500}]
        request = self._request(conn, requester, vendor["id"], lines)
        self.assertEqual(4 * 2500, request["total_cents"])
        self.assertEqual(1, request["version"])
        self.assertEqual(0, self._approvals(conn))
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
        self.assertEqual(3, approved["version"])
        self.assertEqual(1, self._approvals(conn))
        approval_row = conn.execute("SELECT * FROM approvals").fetchone()
        self.assertEqual("approved", approval_row["decision"])
        self.assertEqual(10000, approval_row["approved_total_cents"])
        self.assertEqual("user-999", approval_row["approver_id"])
        self.assertIsNotNone(approval_row["decided_at"])
        self.assertIsNone(approval_row["invalidated_at"])

    def test_t2_requester_cannot_approve_even_when_role_is_approver(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        self._seed_users(conn)
        requester = self._context(actor_id="user-111")
        vendor = self._vendor(conn, requester)
        bolt = self._part(conn, requester, sku="bolt-m8", name="M8 bolt")
        lines = [{"part_id": bolt["id"], "quantity": 2, "unit_cost_cents": 500}]
        request = self._request(conn, requester, vendor["id"], lines)
        submit_ok = submit_purchase_request(
            conn, requester,
            purchase_request_id=request["id"], expected_version=1,
            clock=self._tick_clock(),
        )
        self.assertEqual("submitted", submit_ok["status"])
        with conn:
            conn.execute(
                "UPDATE memberships SET role = ? WHERE organization_id = ? AND user_id = ?",
                ("approver", "org-aaa", "user-111"),
            )
        with self.assertRaises(PermissionDeniedError) as caught:
            approve_purchase_request(
                conn, self._context(actor_id="user-111"),
                purchase_request_id=request["id"], expected_version=2,
                clock=self._tick_clock(),
            )
        self.assertIn("own purchase request", str(caught.exception))
        fetched = conn.execute(
            "SELECT * FROM purchase_requests WHERE id = ?", (request["id"],)
        ).fetchone()
        self.assertEqual("submitted", fetched["status"])
        self.assertEqual(2, fetched["version"])
        self.assertEqual(0, self._approvals(conn))

    def test_t3_actor_without_approver_membership_is_denied(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        self._seed_users(conn)
        requester = self._context(actor_id="user-111")
        outsider = self._context(actor_id="user-777")
        vendor = self._vendor(conn, requester)
        bolt = self._part(conn, requester, sku="bolt-m8", name="M8 bolt")
        lines = [{"part_id": bolt["id"], "quantity": 1, "unit_cost_cents": 2500}]
        request = self._request(conn, requester, vendor["id"], lines)
        submit_ok = submit_purchase_request(
            conn, requester,
            purchase_request_id=request["id"], expected_version=1,
            clock=self._tick_clock(),
        )
        self.assertEqual("submitted", submit_ok["status"])
        with self.assertRaises(PermissionDeniedError) as caught:
            approve_purchase_request(
                conn, outsider,
                purchase_request_id=request["id"], expected_version=2,
                clock=self._tick_clock(),
            )
        self.assertIn("purchase.approve", str(caught.exception))
        fetched = conn.execute(
            "SELECT * FROM purchase_requests WHERE id = ?", (request["id"],)
        ).fetchone()
        self.assertEqual("submitted", fetched["status"])
        self.assertEqual(0, self._approvals(conn))

    def test_t4_reject_flow_records_a_rejection_row(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        self._seed_users(conn)
        self._seed_membership(conn, "user-999", "approver")
        requester = self._context(actor_id="user-111")
        approver = self._context(actor_id="user-999")
        vendor = self._vendor(conn, requester)
        bolt = self._part(conn, requester, sku="bolt-m8", name="M8 bolt")
        lines = [{"part_id": bolt["id"], "quantity": 2, "unit_cost_cents": 1000}]
        request = self._request(conn, requester, vendor["id"], lines)
        submitted = submit_purchase_request(
            conn, requester,
            purchase_request_id=request["id"], expected_version=1,
            clock=self._tick_clock(),
        )
        self.assertEqual("submitted", submitted["status"])
        rejected = reject_purchase_request(
            conn, approver,
            purchase_request_id=request["id"], expected_version=2,
            clock=self._tick_clock(), reason="wrong vendor",
        )
        self.assertEqual("rejected", rejected["status"])
        self.assertEqual(3, rejected["version"])
        self.assertEqual(1, self._approvals(conn))
        approval_row = conn.execute("SELECT * FROM approvals").fetchone()
        self.assertEqual("rejected", approval_row["decision"])
        self.assertEqual(2000, approval_row["approved_total_cents"])
        self.assertEqual("user-999", approval_row["approver_id"])
        self.assertIsNotNone(approval_row["decided_at"])
        self.assertIsNone(approval_row["invalidated_at"])

    def test_t5_stale_expected_version_conflict_on_decision(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        self._seed_users(conn)
        self._seed_membership(conn, "user-999", "approver")
        requester = self._context(actor_id="user-111")
        approver = self._context(actor_id="user-999")
        vendor = self._vendor(conn, requester)
        bolt = self._part(conn, requester, sku="bolt-m8", name="M8 bolt")
        lines = [{"part_id": bolt["id"], "quantity": 1, "unit_cost_cents": 100}]
        request = self._request(conn, requester, vendor["id"], lines)
        submitted = submit_purchase_request(
            conn, requester,
            purchase_request_id=request["id"], expected_version=1,
            clock=self._tick_clock(),
        )
        self.assertEqual("submitted", submitted["status"])
        with self.assertRaises(ConflictError):
            approve_purchase_request(
                conn, approver,
                purchase_request_id=request["id"], expected_version=7,
                clock=self._tick_clock(),
            )
        self.assertEqual(0, self._approvals(conn))

    def test_t6_cancel_from_draft_and_from_submitted(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        self._seed_users(conn)
        requester = self._context(actor_id="user-111")
        vendor = self._vendor(conn, requester)
        bolt = self._part(conn, requester, sku="bolt-m8", name="M8 bolt")
        lines = [{"part_id": bolt["id"], "quantity": 1, "unit_cost_cents": 500}]

        draft = self._request(conn, requester, vendor["id"], lines)
        cancelled_draft = cancel_purchase_request(
            conn, requester,
            purchase_request_id=draft["id"], expected_version=1,
            clock=self._tick_clock(),
        )
        self.assertEqual("cancelled", cancelled_draft["status"])
        self.assertEqual(2, cancelled_draft["version"])

        submitted = self._request(conn, requester, vendor["id"], lines)
        submitted_row = submit_purchase_request(
            conn, requester,
            purchase_request_id=submitted["id"], expected_version=1,
            clock=self._tick_clock(),
        )
        self.assertEqual("submitted", submitted_row["status"])
        cancelled_submitted = cancel_purchase_request(
            conn, requester,
            purchase_request_id=submitted["id"], expected_version=2,
            clock=self._tick_clock(),
        )
        self.assertEqual("cancelled", cancelled_submitted["status"])
        self.assertEqual(3, cancelled_submitted["version"])


if __name__ == "__main__":
    unittest.main()
