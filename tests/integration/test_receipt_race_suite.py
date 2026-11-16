"""Integration tests (T046): the receipt race suite.

Mirrors the landed two-connection race pattern exactly: two independent
SQLite connections (EACH created inside its own thread, never shared),
a threading.Barrier to align them, and NO process-local lock --
correctness comes from the guarded conditional order UPDATE inside the
receipt service's ONE explicit transaction. Uses the REAL shipped
migrations against a temporary file database (no CREATE TABLE) and a
_tick_clock helper giving each call a DISTINCT FixedClock timestamp
(UTC, RFC3339 Z, second precision; never a fixed timestamp).
"""

import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone

from opsledger.core import OrganizationContext
from opsledger.core.clock import format_rfc3339
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect
from opsledger.core.errors import ConflictError
from opsledger.core.migrations import migrate
from opsledger.parts import create_part, create_stock_location
from opsledger.inventory import reconcile_balance
from opsledger.purchasing.lifecycle import (
    approve_purchase_request,
    submit_purchase_request,
)
from opsledger.purchasing.orders import issue_order
from opsledger.purchasing.receipts import outstanding_quantity, receive_order
from opsledger.purchasing.requests import create_purchase_request
from opsledger.purchasing.vendors import create_vendor


class ReceiptRaceSuiteTest(unittest.TestCase):
    def setUp(self):
        self._clock_tick = 0
        self._tick_lock = threading.Lock()

    def _open_migrated(self):
        """Temporary file database with the REAL shipped migrations (no CREATE TABLE)."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda: connect(tmp.name).close())
        seed_conn = connect(tmp.name)
        self.addCleanup(seed_conn.close)
        migrate(seed_conn, "opsledger/migrations")
        self._db_path = tmp.name
        return seed_conn

    def _tick_clock(self):
        """Each call gets a DISTINCT clock instant: UTC, RFC3339 Z, seconds."""
        with self._tick_lock:
            self._clock_tick += 1
            tick = self._clock_tick
        return FixedClock(datetime.now(timezone.utc) + timedelta(seconds=tick))

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

    def _open_order(self, conn, context, quantity=10):
        """Seed submit + approve with a dedicated approver, then issue one open order."""
        approver = self._context(actor_id="user-999")
        vendor = self._vendor(conn, context)
        part = self._part(conn, context, sku="bolt-m8", name="M8 bolt")
        location = self._location(conn, context)
        lines = [{"part_id": part["id"], "quantity": quantity, "unit_cost_cents": 2500}]
        request = self._request(conn, context, vendor["id"], lines)
        submitted = self._submit(conn, context, request["id"], 1)
        self.assertEqual("submitted", submitted["status"])
        approved = self._approve(conn, approver, request["id"], 2)
        self.assertEqual("approved", approved["status"])
        order, _record, _replayed = self._issue(conn, context, approved["id"], 3)
        return order, part, location

    def test_t1_app04_concurrent_same_key_receipt_admits_one(self):
        seed_conn = self._open_migrated()
        self._seed_organization(seed_conn)
        self._seed_users(seed_conn)
        self._seed_membership(seed_conn, "user-999", "approver")
        context = self._context()
        order, part, location = self._open_order(seed_conn, context, quantity=10)
        barrier = threading.Barrier(2)
        results = {}
        errors = []

        def worker(index):
            worker_conn = connect(self._db_path)
            try:
                barrier.wait()
                receipt, _record, replayed = receive_order(
                    worker_conn, context, purchase_order_id=order["id"],
                    stock_location_id=location["id"],
                    lines=[{"part_id": part["id"], "quantity": 3}],
                    expected_version=1, actor_id=context.actor_id,
                    clock=self._tick_clock(), idempotency_key="key-app04",
                )
                results[index] = ("ok", receipt["id"], replayed)
            except ConflictError as exc:
                results[index] = ("conflict", None, False, exc.code)
            except Exception as error:  # pragma: no cover - diagnostic path
                errors.append(error)
            finally:
                worker_conn.close()

        threads = [threading.Thread(target=worker, args=(index,)) for index in (0, 1)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertEqual([], errors)
        self.assertEqual(2, len(results))
        ok_results = [entry for entry in results.values() if entry[0] == "ok"]
        conflict_results = [entry for entry in results.values() if entry[0] == "conflict"]
        self.assertEqual(2, len(ok_results))
        self.assertEqual(0, len(conflict_results))
        self.assertEqual(1, seed_conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0])
        self.assertEqual(1, seed_conn.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0])
        balance = seed_conn.execute(
            "SELECT on_hand FROM stock_balances WHERE part_id = ?", (part["id"],)
        ).fetchone()
        self.assertEqual(3, balance["on_hand"])
        replayed_flags = [entry[2] for entry in ok_results]
        self.assertEqual(1, replayed_flags.count(True))
        self.assertEqual(1, replayed_flags.count(False))

    def test_t2_app05_app11_different_key_over_receipt_race_admits_ordered(self):
        seed_conn = self._open_migrated()
        self._seed_organization(seed_conn)
        self._seed_users(seed_conn)
        self._seed_membership(seed_conn, "user-999", "approver")
        context = self._context()
        order, part, location = self._open_order(seed_conn, context, quantity=10)
        barrier = threading.Barrier(2)
        results = {}
        errors = []

        def worker(index):
            worker_conn = connect(self._db_path)
            lines = [{"part_id": part["id"], "quantity": 6 if index == 0 else 7}]
            key = "key-app05-a" if index == 0 else "key-app05-b"
            try:
                barrier.wait()
                receipt, _record, replayed = receive_order(
                    worker_conn, context, purchase_order_id=order["id"],
                    stock_location_id=location["id"], lines=lines,
                    expected_version=1, actor_id=context.actor_id,
                    clock=self._tick_clock(), idempotency_key=key,
                )
                results[index] = ("ok", receipt["id"], replayed)
            except ConflictError as exc:
                results[index] = ("conflict", None, str(exc))
            except Exception as error:  # pragma: no cover - diagnostic path
                errors.append(error)
            finally:
                worker_conn.close()

        threads = [threading.Thread(target=worker, args=(index,)) for index in (0, 1)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertEqual([], errors)
        self.assertEqual(2, len(results))
        ok_results = [entry for entry in results.values() if entry[0] == "ok"]
        conflict_results = [entry for entry in results.values() if entry[0] == "conflict"]
        self.assertEqual(1, len(ok_results))
        self.assertEqual(1, len(conflict_results))
        self.assertIn(
            conflict_results[0][2],
            {
                "receipt quantity exceeds the outstanding order quantity",
                "purchase order version conflict; refresh and retry",
            },
        )
        self.assertEqual(1, seed_conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0])
        outstanding = outstanding_quantity(
            seed_conn, context, order_id=order["id"], part_id=part["id"]
        )
        admitted = admitted_total(seed_conn)
        self.assertLessEqual(admitted, 10)
        self.assertGreaterEqual(outstanding[2], 0)
        self.assertEqual(admitted, 10 - outstanding[2])
        reconciled = reconcile_balance(
            seed_conn, context, part_id=part["id"], location_id=location["id"],
            clock=self._tick_clock(),
        )
        self.assertTrue(reconciled["matches"])
        self.assertEqual(admitted, reconciled["on_hand_sum"])

    def test_t3_stale_expected_version_refused_stores_nothing(self):
        seed_conn = self._open_migrated()
        self._seed_organization(seed_conn)
        self._seed_users(seed_conn)
        self._seed_membership(seed_conn, "user-999", "approver")
        context = self._context()
        order, part, location = self._open_order(seed_conn, context, quantity=10)
        with self.assertRaises(ConflictError) as caught:
            receive_order(
                seed_conn, context, purchase_order_id=order["id"],
                stock_location_id=location["id"],
                lines=[{"part_id": part["id"], "quantity": 3}],
                expected_version=999, actor_id=context.actor_id,
                clock=self._tick_clock(), idempotency_key="key-stale",
            )
        self.assertEqual("conflict", caught.exception.code)
        self.assertEqual("purchase order version conflict; refresh and retry", str(caught.exception))
        self.assertEqual(0, receipt_row_count(seed_conn))
        self.assertEqual(0, movement_row_count(seed_conn))

    def test_t4_refused_receipt_changes_nothing(self):
        seed_conn = self._open_migrated()
        self._seed_organization(seed_conn)
        self._seed_users(seed_conn)
        self._seed_membership(seed_conn, "user-999", "approver")
        context = self._context()
        order, part, location = self._open_order(seed_conn, context, quantity=10)
        before_receipts = receipt_row_count(seed_conn)
        before_movements = movement_row_count(seed_conn)
        with self.assertRaises(ConflictError) as refused:
            receive_order(
                seed_conn, context, purchase_order_id=order["id"],
                stock_location_id=location["id"],
                lines=[{"part_id": part["id"], "quantity": 12}],
                expected_version=1, actor_id=context.actor_id,
                clock=self._tick_clock(), idempotency_key="key-refused",
            )
        self.assertEqual("receipt quantity exceeds the outstanding order quantity", str(refused.exception))
        self.assertEqual(before_receipts, receipt_row_count(seed_conn))
        self.assertEqual(before_movements, movement_row_count(seed_conn))
        self.assertEqual(0, seed_conn.execute("SELECT COUNT(*) FROM stock_balances").fetchone()[0])
        statuses = [
            row[0]
            for row in seed_conn.execute(
                "SELECT status FROM idempotency_records WHERE operation = 'purchase.receive_order'"
            ).fetchall()
        ]
        self.assertEqual(["failed"], sorted(statuses))


def receipt_row_count(conn):
    return conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]


def movement_row_count(conn):
    return conn.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0]


def admitted_total(conn):
    return conn.execute(
        "SELECT COALESCE(SUM(quantity), 0) FROM receipt_lines WHERE archived_at IS NULL"
    ).fetchone()[0]


if __name__ == "__main__":
    unittest.main()
