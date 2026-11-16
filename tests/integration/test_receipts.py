"""Integration tests (T045): stock receipts against open purchase orders.

Uses the REAL shipped migrations against a temporary file database (no
CREATE TABLE) and drives the receipt service through its public
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
from opsledger.core.errors import ConflictError
from opsledger.core.migrations import migrate
from opsledger.inventory import list_movements, reconcile_balance
from opsledger.parts import create_part, create_stock_location
from opsledger.purchasing.lifecycle import approve_purchase_request, submit_purchase_request
from opsledger.purchasing.orders import issue_order
from opsledger.purchasing.receipts import (
    OVER_RECEIPT_MESSAGE,
    receive_order,
    outstanding_quantity,
)
from opsledger.purchasing.requests import create_purchase_request
from opsledger.purchasing.vendors import create_vendor


class ReceiptTest(unittest.TestCase):
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

    def _location(self, conn, context, code="STO-1"):
        return create_stock_location(conn, context, code=code, name="Main store", clock=self._tick_clock())

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

    def _receive(self, conn, context, purchase_order_id, stock_location_id, lines, expected_version, idempotency_key):
        return receive_order(
            conn, context, purchase_order_id=purchase_order_id,
            stock_location_id=stock_location_id, lines=lines,
            expected_version=expected_version, actor_id=context.actor_id,
            clock=self._tick_clock(), idempotency_key=idempotency_key,
        )

    def _open_order(self, conn, context, quantity=10):
        """Seed submit + approve with a dedicated approver, then issue one open order."""
        approver = self._context(actor_id="user-999")
        vendor = self._vendor(conn, context)
        bolt = self._part(conn, context, sku="bolt-m8", name="M8 bolt")
        loc = self._location(conn, context)
        lines = [{"part_id": bolt["id"], "quantity": quantity, "unit_cost_cents": 2500}]
        request = self._request(conn, context, vendor["id"], lines)
        submitted = self._submit(conn, context, request["id"], 1)
        self.assertEqual("submitted", submitted["status"])
        approved = self._approve(conn, approver, request["id"], 2)
        self.assertEqual("approved", approved["status"])
        order, _record, _replayed = self._issue(conn, context, approved["id"], 3)
        return order, bolt, loc

    def test_t1_partial_receipt_then_same_key_stale_version_replays_once(self):
        conn = self._open_migrated()
        self._seed_organization(conn)
        self._seed_users(conn)
        self._seed_membership(conn, "user-999", "approver")
        context = self._context()
        order, bolt, loc = self._open_order(conn, context, quantity=10)
        receipt, _record, replayed = self._receive(
            conn, context, order["id"], loc["id"],
            [{"part_id": bolt["id"], "quantity": 4}], 1, "key-receipt-1",
        )
        self.assertFalse(replayed)
        self.assertEqual("received", receipt["status"])
        balance = conn.execute(
            "SELECT on_hand, reserved FROM stock_balances WHERE part_id = ?", (bolt["id"],)
        ).fetchone()
        self.assertEqual((4, 0), (balance["on_hand"], balance["reserved"]))
        movements = list_movements(conn, context, part_id=bolt["id"], location_id=loc["id"])
        self.assertEqual(1, len(movements))
        self.assertEqual("receive", movements[0]["operation"])
        self.assertEqual(4, movements[0]["on_hand_delta"])
        replay, _replay_record, replayed = self._receive(
            conn, context, order["id"], loc["id"],
            [{"part_id": bolt["id"], "quantity": 4}], 999, "key-receipt-1",
        )
        self.assertTrue(replayed)
        self.assertEqual(receipt["id"], replay["id"])
        balance = conn.execute(
            "SELECT on_hand, reserved FROM stock_balances WHERE part_id = ?", (bolt["id"],)
        ).fetchone()
        self.assertEqual((4, 0), (balance["on_hand"], balance["reserved"]))
        self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0])
        self.assertEqual(
            1, len(list_movements(conn, context, part_id=bolt["id"], location_id=loc["id"]))
        )

    def test_t2_outstanding_quantity_then_over_receipt_rejected_changes_nothing(self):
        conn = self._open_migrated()
        self._seed_organization(conn)
        self._seed_users(conn)
        self._seed_membership(conn, "user-999", "approver")
        context = self._context()
        order, bolt, loc = self._open_order(conn, context, quantity=10)
        self._receive(
            conn, context, order["id"], loc["id"],
            [{"part_id": bolt["id"], "quantity": 4}], 1, "key-receipt-2",
        )
        self.assertEqual(
            (10, 4, 6), outstanding_quantity(conn, context, order_id=order["id"], part_id=bolt["id"])
        )
        with self.assertRaises(ConflictError) as caught:
            self._receive(
                conn, context, order["id"], loc["id"],
                [{"part_id": bolt["id"], "quantity": 7}], 2, "key-receipt-2b",
            )
        self.assertEqual(OVER_RECEIPT_MESSAGE, str(caught.exception))
        self.assertEqual(
            (10, 4, 6), outstanding_quantity(conn, context, order_id=order["id"], part_id=bolt["id"])
        )
        self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0])
        reconciled = reconcile_balance(
            conn, context, part_id=bolt["id"], location_id=loc["id"], clock=self._tick_clock()
        )
        self.assertTrue(reconciled["matches"])
        self.assertEqual(4, reconciled["on_hand_sum"])

    def test_t3_one_receipt_commits_all_writes_in_one_transaction(self):
        conn = self._open_migrated()
        self._seed_organization(conn)
        self._seed_users(conn)
        self._seed_membership(conn, "user-999", "approver")
        context = self._context()
        order, bolt, loc = self._open_order(conn, context, quantity=10)
        self._receive(
            conn, context, order["id"], loc["id"],
            [{"part_id": bolt["id"], "quantity": 4}], 1, "key-receipt-3",
        )
        self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0])
        self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM receipt_lines").fetchone()[0])
        self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0])
        self.assertEqual(4, conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0])
        self.assertEqual(2, conn.execute("SELECT COUNT(*) FROM idempotency_records").fetchone()[0])
        statuses = [row[0] for row in conn.execute("SELECT status FROM idempotency_records").fetchall()]
        self.assertEqual(["completed", "completed"], sorted(statuses))
