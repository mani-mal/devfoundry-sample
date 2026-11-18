"""Golden-journey integration tests (T048): stock shortage through repair.

Seeds two organizations plus a purchasing actor and an approver, then
drives the stock-shortage-to-repair story through the PUBLIC service
functions only: an opening adjustment, a refused reservation against
the shortage, an approved purchase with a partial receipt, the repair
reservations, and recorded labor. Asserts the export view of the same
journey (both the outstanding quantity and the export module's own
read-only view). Uses the REAL shipped migrations against a temporary
file database (no CREATE TABLE) and a _tick_clock helper giving every
call a FRESH DISTINCT clock instant (UTC, RFC3339 Z, second precision;
no fixed timestamps anywhere in this file).
"""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from opsledger.assets import create_asset, create_site
from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock, format_rfc3339
from opsledger.core.db import connect
from opsledger.core.errors import ConflictError
from opsledger.core.migrations import migrate
from opsledger.inventory import (
    adjust_stock,
    consume_reservation,
    reconcile_balance,
    release_reservation,
    reserve_stock,
)
from opsledger.parts import create_part, create_stock_location
from opsledger.purchasing.lifecycle import approve_purchase_request, submit_purchase_request
from opsledger.purchasing.orders import issue_order
from opsledger.purchasing.receipts import outstanding_quantity, receive_order
from opsledger.purchasing.requests import create_purchase_request
from opsledger.purchasing.recon_export import export_purchasing, order_outstanding, receipt_history
from opsledger.purchasing.vendors import create_vendor
from opsledger.workorders import create_work_order, record_labor


class GoldenJourneyTest(unittest.TestCase):
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

    def _seed_organization(self, conn, organization_id):
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
                ("user-111", "user-111@example.com", "Purchasing One", created_text),
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

    def _stock_location(self, conn, context, code="STO-1"):
        return create_stock_location(
            conn, context, code=code, name="Main store", clock=self._tick_clock(),
        )

    def _site(self, conn, context, code="site-1"):
        return create_site(conn, context, code=code, name="Main site", clock=self._tick_clock())

    def _asset(self, conn, context, site_id):
        return create_asset(
            conn, context, site_id=site_id, tag="pump-1", name="Coolant pump",
            criticality="high", purchase_cost_cents=10000, clock=self._tick_clock(),
        )

    def _work_order(self, conn, context, site_id, asset_id):
        return create_work_order(
            conn, context, site_id=site_id, asset_id=asset_id, number="wo-100",
            title="Replace pump seals", description="Pump seals are leaking",
            priority="high", requester_id="user-111", clock=self._tick_clock(),
        )

    def _purchase_request(self, conn, context, vendor_id, lines):
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

    def _issue(self, conn, context, purchase_request_id, expected_version, idempotency_key):
        return issue_order(
            conn, context, purchase_request_id=purchase_request_id,
            expected_version=expected_version, actor_id="user-111",
            clock=self._tick_clock(), idempotency_key=idempotency_key,
        )

    def _receive(self, conn, context, purchase_order_id, stock_location_id, lines, expected_version, idempotency_key):
        return receive_order(
            conn, context, purchase_order_id=purchase_order_id,
            stock_location_id=stock_location_id, lines=lines,
            expected_version=expected_version, actor_id="user-111",
            clock=self._tick_clock(), idempotency_key=idempotency_key,
        )

    def _reserve(self, conn, context, part_id, location_id, work_order_id, quantity, expected_version):
        return reserve_stock(
            conn, context, part_id=part_id, location_id=location_id,
            work_order_id=work_order_id, quantity=quantity,
            expected_version=expected_version, actor_id="user-111",
            clock=self._tick_clock(),
        )

    def test_t048_golden_journey_stock_shortage_to_repair_with_export_view(self):
        conn = self._open_migrated()
        self._seed_organization(conn, "org-aaa")
        self._seed_organization(conn, "org-bbb")
        self._seed_users(conn)
        self._seed_membership(conn, "user-111", "purchasing")
        self._seed_membership(conn, "user-999", "approver")
        context = self._context()
        approver = self._context(actor_id="user-999")

        part = self._part(conn, context, sku="bolt-m8", name="M8 bolt")
        location = self._stock_location(conn, context)
        vendor = self._vendor(conn, context)
        site = self._site(conn, context)
        asset = self._asset(conn, context, site_id=site["id"])
        work_order = self._work_order(conn, context, site_id=site["id"], asset_id=asset["id"])

        adjusted = adjust_stock(
            conn, context, part_id=part["id"], location_id=location["id"],
            quantity_delta=1, reason="opening", expected_version=1,
            actor_id="user-111", clock=self._tick_clock(),
        )
        self.assertEqual(1, adjusted["on_hand"])
        self.assertEqual(0, adjusted["reserved"])

        with self.assertRaises(ConflictError):
            self._reserve(
                conn, context, part_id=part["id"], location_id=location["id"],
                work_order_id=work_order["id"], quantity=2, expected_version=2,
            )

        lines = [{"part_id": part["id"], "quantity": 10, "unit_cost_cents": 2500}]
        request = self._purchase_request(conn, context, vendor_id=vendor["id"], lines=lines)
        submitted = self._submit(conn, context, purchase_request_id=request["id"], expected_version=1)
        self.assertEqual("submitted", submitted["status"])
        approved = self._approve(conn, approver, purchase_request_id=request["id"], expected_version=2)
        self.assertEqual("approved", approved["status"])
        order, _issue_record, order_replayed = self._issue(
            conn, context, purchase_request_id=approved["id"], expected_version=3,
            idempotency_key="issue-golden",
        )
        self.assertFalse(order_replayed)
        self.assertEqual("open", order["status"])
        self.assertEqual(25000, order["total_cents"])
        self.assertEqual(1, order["version"])

        receipt, _receipt_record, receipt_replayed = self._receive(
            conn, context, purchase_order_id=order["id"], stock_location_id=location["id"],
            lines=[{"part_id": part["id"], "quantity": 4}], expected_version=order["version"],
            idempotency_key="rcpt-golden",
        )
        self.assertFalse(receipt_replayed)
        self.assertEqual("received", receipt["status"])

        repair = self._reserve(
            conn, context, part_id=part["id"], location_id=location["id"],
            work_order_id=work_order["id"], quantity=2, expected_version=3,
        )
        self.assertEqual(2, repair["remaining_quantity"])
        self.assertEqual("active", repair["status"])
        consumed = consume_reservation(
            conn, context, reservation_id=repair["id"], quantity=1,
            expected_version=4, actor_id="user-111", clock=self._tick_clock(),
        )
        self.assertEqual(1, consumed["remaining_quantity"])
        released = release_reservation(
            conn, context, reservation_id=repair["id"], quantity=1,
            expected_version=5, actor_id="user-111", clock=self._tick_clock(),
        )
        self.assertEqual("released", released["status"])
        self.assertEqual(0, released["remaining_quantity"])

        labor = record_labor(
            conn, context, work_order_id=work_order["id"], technician_id="user-111",
            minutes=90, rate_cents_per_hour=8000, clock=self._tick_clock(),
        )
        self.assertEqual(12000, labor["cost_cents"])
        self.assertEqual(90, labor["minutes"])

        balance_row = conn.execute(
            "SELECT on_hand, reserved FROM stock_balances WHERE part_id = ?", (part["id"],)
        ).fetchone()
        self.assertEqual((4, 0), (balance_row["on_hand"], balance_row["reserved"]))

        self.assertEqual(
            (10, 4, 6), outstanding_quantity(conn, context, order_id=order["id"], part_id=part["id"])
        )

        history = receipt_history(conn, context, purchase_order_id=order["id"])
        self.assertEqual(1, len(history))
        self.assertEqual(10000, history[0]["cost_cents"])
        self.assertEqual("received", history[0]["receipt"]["status"])
        self.assertEqual(4, history[0]["lines"][0]["quantity"])
        self.assertEqual(2500, history[0]["lines"][0]["unit_cost_cents"])

        reconciled = reconcile_balance(
            conn, context, part_id=part["id"], location_id=location["id"],
            clock=self._tick_clock(),
        )
        self.assertTrue(reconciled["matches"])
        self.assertEqual(4, reconciled["on_hand_sum"])
        self.assertEqual(0, reconciled["reserved_sum"])

        export = export_purchasing(conn, context)
        serialized = json.dumps(export, sort_keys=True, default=dict)
        self.assertIn("Acme", serialized)
        self.assertIn("approved", serialized)

        view = order_outstanding(conn, context, purchase_order_id=order["id"])
        self.assertEqual(1, len(view))
        self.assertEqual(part["id"], view[0]["part_id"])
        self.assertEqual(10, view[0]["ordered"])
        self.assertEqual(4, view[0]["received"])
        self.assertEqual(6, view[0]["outstanding"])

        replay, _replay_record, replayed = self._receive(
            conn, context, purchase_order_id=order["id"], stock_location_id=location["id"],
            lines=[{"part_id": part["id"], "quantity": 4}], expected_version=999,
            idempotency_key="rcpt-golden",
        )
        self.assertTrue(replayed)
        self.assertEqual(receipt["id"], replay["id"])

        balance_row = conn.execute(
            "SELECT on_hand, reserved FROM stock_balances WHERE part_id = ?", (part["id"],)
        ).fetchone()
        self.assertEqual((4, 0), (balance_row["on_hand"], balance_row["reserved"]))

        self.assertEqual(
            (10, 4, 6), outstanding_quantity(conn, context, order_id=order["id"], part_id=part["id"])
        )

        self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0])
        self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM labor_entries").fetchone()[0])

    def test_t048_export_purchasing_serializes_and_scopes_per_organization(self):
        conn = self._open_migrated()
        self._seed_organization(conn, "org-aaa")
        self._seed_organization(conn, "org-bbb")
        self._seed_users(conn)
        self._seed_membership(conn, "user-111", "purchasing")
        self._seed_membership(conn, "user-999", "approver")
        context = self._context()
        approver = self._context(actor_id="user-999")

        part = self._part(conn, context, sku="bolt-m8", name="M8 bolt")
        location = self._stock_location(conn, context)
        vendor = self._vendor(conn, context)

        lines = [{"part_id": part["id"], "quantity": 10, "unit_cost_cents": 2500}]
        request = self._purchase_request(conn, context, vendor_id=vendor["id"], lines=lines)
        self._submit(conn, context, purchase_request_id=request["id"], expected_version=1)
        self._approve(conn, approver, purchase_request_id=request["id"], expected_version=2)
        self._issue(
            conn, context, purchase_request_id=request["id"], expected_version=3,
            idempotency_key="issue-scoped",
        )

        self.assertEqual(
            {"vendors": [], "purchase_requests": [], "purchase_orders": []},
            export_purchasing(conn, self._context(organization_id="org-bbb")),
        )

        exported = export_purchasing(conn, context)
        serialized = json.dumps(exported, sort_keys=True, default=dict)
        self.assertIn("Acme", serialized)
        self.assertIn("total_cents", serialized)
