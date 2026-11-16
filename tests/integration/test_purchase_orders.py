"""Integration tests (T044): idempotent purchase-order issue.

Uses the REAL shipped migrations against a temporary file database (no
CREATE TABLE) and drives the order service through its public
functions only, with a _tick_clock helper giving every call a FRESH
DISTINCT clock instant (UTC, RFC3339 Z, second precision; no fixed
timestamps anywhere in this file).
"""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock, format_rfc3339
from opsledger.core.db import connect
from opsledger.core.errors import ConflictError, ValidationError
from opsledger.core.migrations import migrate
from opsledger.parts import create_part
from opsledger.purchasing.lifecycle import (
    approve_purchase_request,
    cancel_purchase_request,
    reject_purchase_request,
    submit_purchase_request,
)
from opsledger.purchasing.orders import (
    CANCELLED_REQUEST_MESSAGE,
    REQUEST_NOT_APPROVED_MESSAGE,
    get_order,
    issue_order,
    list_order_lines,
)
from opsledger.purchasing.requests import create_purchase_request
from opsledger.purchasing.vendors import create_vendor


class PurchaseOrderIssueTest(unittest.TestCase):
    def setUp(self):
        self._clock_tick = 0

    def _open_migrated(self):
        """Open a temporary file database with the REAL shipped migrations (no CREATE TABLE)."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
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
                ("user-999", "user-999@example.com", "Approver Nine", created_text),
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

    def _submit(self, conn, context, purchase_request_id, expected_version):
        return submit_purchase_request(
            conn, context, purchase_request_id=purchase_request_id,
            expected_version=expected_version, clock=self._tick_clock(),
        )

    def _approve(self, conn, context, purchase_request_id, expected_version):
        return approve_purchase_request(
            conn, context, purchase_request_id=purchase_request_id,
            expected_version=expected_version, clock=self._tick_clock(),
        )

    def _issue(self, conn, context, purchase_request_id, expected_version, idempotency_key="key-1"):
        return issue_order(
            conn, context, purchase_request_id=purchase_request_id,
            expected_version=expected_version, actor_id=context.actor_id,
            clock=self._tick_clock(), idempotency_key=idempotency_key,
        )

    def _submitted_and_approved(self, conn, context):
        """Submit then approve with a dedicated approver (user-999)."""
        approver = self._context(actor_id="user-999")
        vendor = self._vendor(conn, context)
        bolt = self._part(conn, context, sku="bolt-m8", name="M8 bolt")
        lines = [{"part_id": bolt["id"], "quantity": 10, "unit_cost_cents": 2500}]
        request = self._request(conn, context, vendor["id"], lines)
        submitted = submit_purchase_request(
            conn, context, purchase_request_id=request["id"],
            expected_version=1, clock=self._tick_clock(),
        )
        self.assertEqual("submitted", submitted["status"])
        approved = approve_purchase_request(
            conn, approver, purchase_request_id=request["id"],
            expected_version=2, clock=self._tick_clock(),
        )
        self.assertEqual("approved", approved["status"])
        return approved

    def _orders(self, conn):
        return conn.execute("SELECT COUNT(*) FROM purchase_orders").fetchone()[0]

    def _records(self, conn):
        return conn.execute("SELECT COUNT(*) FROM idempotency_records").fetchone()[0]

    def test_t1_issue_from_approved_request_records_one_open_order(self):
        conn = self._open_migrated()
        self._seed_organization(conn)
        self._seed_users(conn)
        self._seed_membership(conn, "user-999", "approver")
        context = self._context()
        approved = self._submitted_and_approved(conn, context)
        self.assertEqual(3, approved["version"])
        order, record, replayed = self._issue(conn, context, approved["id"], 3)
        self.assertFalse(replayed)
        self.assertEqual("open", order["status"])
        self.assertEqual(25000, order["total_cents"])
        self.assertEqual(1, order["version"])
        self.assertEqual("user-111", order["issued_by"])
        self.assertIsNone(order["archived_at"])
        self.assertEqual(1, self._orders(conn))
        fetched = get_order(conn, context, order["id"])
        self.assertEqual("open", fetched["status"])
        lines = list_order_lines(conn, context, purchase_order_id=order["id"])
        self.assertEqual(1, len(lines))
        self.assertEqual(10, lines[0]["quantity"])
        self.assertEqual(2500, lines[0]["unit_cost_cents"])
        self.assertIsNotNone(record)
        self.assertEqual("completed", record["status"])
        self.assertEqual(1, self._records(conn))

    def test_t2_issue_marks_request_ordered(self):
        conn = self._open_migrated()
        self._seed_organization(conn)
        self._seed_users(conn)
        self._seed_membership(conn, "user-999", "approver")
        context = self._context()
        approved = self._submitted_and_approved(conn, context)
        order, _order_record, _replayed = self._issue(conn, context, approved["id"], 3)
        fetched = get_order(conn, context, order["id"])
        self.assertEqual("open", fetched["status"])
        row = conn.execute(
            "SELECT status, version FROM purchase_requests WHERE id = ?", (approved["id"],)
        ).fetchone()
        self.assertEqual("ordered", row[0])
        self.assertEqual(4, row[1])

    def test_t3_same_key_stale_version_replays_prior_order(self):
        conn = self._open_migrated()
        self._seed_organization(conn)
        self._seed_users(conn)
        self._seed_membership(conn, "user-999", "approver")
        context = self._context()
        approved = self._submitted_and_approved(conn, context)
        order, _record, _replayed = self._issue(conn, context, approved["id"], 3)
        replay, _replay_record, replayed = self._issue(conn, context, approved["id"], 999)
        self.assertTrue(replayed)
        self.assertEqual(order["id"], replay["id"])
        self.assertEqual(25000, replay["total_cents"])
        self.assertEqual(1, self._orders(conn))
        self.assertEqual(1, self._records(conn))
        all_rows = conn.execute("SELECT COUNT(*) FROM purchase_order_lines").fetchone()[0]
        self.assertEqual(1, all_rows)

    def test_t4_draft_rejected_cancelled_requests_are_refused(self):
        context = self._context()

        def _seed(conn):
            self._seed_organization(conn)
            self._seed_users(conn)
            self._seed_membership(conn, "user-999", "approver")

        # draft: refused
        conn = self._open_migrated()
        _seed(conn)
        vendor = self._vendor(conn, context)
        bolt = self._part(conn, context, sku="bolt-m8", name="M8 bolt")
        lines = [{"part_id": bolt["id"], "quantity": 2, "unit_cost_cents": 2500}]
        draft = self._request(conn, context, vendor["id"], lines)
        with self.assertRaises(ConflictError) as caught:
            self._issue(conn, context, draft["id"], 1)
        self.assertEqual("purchase request is not approved", str(caught.exception))
        self.assertEqual(0, self._orders(conn))

        # rejected: refused
        conn = self._open_migrated()
        _seed(conn)
        vendor = self._vendor(conn, context)
        bolt = self._part(conn, context, sku="bolt-m8", name="M8 bolt")
        lines = [{"part_id": bolt["id"], "quantity": 2, "unit_cost_cents": 2500}]
        request = self._request(conn, context, vendor["id"], lines)
        self._submit(conn, context, request["id"], 1)
        rejected = reject_purchase_request(
            conn, self._context(actor_id="user-999"),
            purchase_request_id=request["id"], expected_version=2,
            clock=self._tick_clock(), reason="no",
        )
        self.assertEqual("rejected", rejected["status"])
        with self.assertRaises(ConflictError) as caught:
            self._issue(conn, context, request["id"], 3)
        self.assertEqual("purchase request is not approved", str(caught.exception))
        self.assertEqual(0, self._orders(conn))

        # cancelled: refused
        conn = self._open_migrated()
        _seed(conn)
        vendor = self._vendor(conn, context)
        bolt = self._part(conn, context, sku="bolt-m8", name="M8 bolt")
        lines = [{"part_id": bolt["id"], "quantity": 2, "unit_cost_cents": 2500}]
        request = self._request(conn, context, vendor["id"], lines)
        cancelled = cancel_purchase_request(
            conn, context,
            purchase_request_id=request["id"], expected_version=1,
            clock=self._tick_clock(),
        )
        self.assertEqual("cancelled", cancelled["status"])
        with self.assertRaises(ConflictError) as caught:
            self._issue(conn, context, request["id"], 2)
        self.assertEqual(CANCELLED_REQUEST_MESSAGE, str(caught.exception))
        self.assertEqual(0, self._orders(conn))

    def test_t5_get_list_scoping_unknown_and_cross_org(self):
        conn = self._open_migrated()
        self._seed_organization(conn)
        self._seed_users(conn)
        self._seed_membership(conn, "user-999", "approver")
        self._seed_organization(conn, "org-bbb")
        context = self._context()
        other = self._context(organization_id="org-bbb")
        approved = self._submitted_and_approved(conn, context)
        order, _record, _replayed = self._issue(conn, context, approved["id"], 3)
        # unknown id: same canonical message
        with self.assertRaises(Exception) as unknown:
            get_order(conn, context, "por-zzz")
        self.assertIn("not found", str(unknown.exception))
        # cross-org id: same canonical message, no leak
        with self.assertRaises(Exception) as cross:
            get_order(conn, other, order["id"])
        self.assertEqual(str(unknown.exception), str(cross.exception))
        # list scoping: unknown order, same owned-lookup error
        with self.assertRaises(Exception) as unknown_lines:
            list_order_lines(conn, context, purchase_order_id="por-zzz")
        self.assertIn("not found", str(unknown_lines.exception))
        with self.assertRaises(Exception) as cross_lines:
            list_order_lines(conn, other, purchase_order_id=order["id"])
        self.assertEqual(str(unknown_lines.exception), str(cross_lines.exception))
