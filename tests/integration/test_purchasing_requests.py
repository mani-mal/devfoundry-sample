"""Integration tests (T041, M6): purchase requests.

Applies the REAL shipped migrations to a temporary file database (no
CREATE TABLE) and exercises the purchase-request service through its
public functions only, with a _tick_clock helper giving each call a
FRESH DISTINCT clock instant (UTC, RFC3339 Z, second precision; no
fixed timestamps anywhere in this file).
"""

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock, format_rfc3339
from opsledger.core.db import connect
from opsledger.core.errors import NotFoundError, ValidationError
from opsledger.core.migrations import migrate
from opsledger.parts import create_part
from opsledger.purchasing.requests import (
    REQUEST_NOT_FOUND_MESSAGE,
    create_purchase_request,
    get_purchase_request,
    list_purchase_requests,
    list_request_lines,
    request_total_cents,
)
from opsledger.purchasing.vendors import create_vendor


class PurchaseRequestsTest(unittest.TestCase):
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
            conn.execute(
                "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                ("org-bbb", "org-bbb", "Organization BBB", created_text),
            )

    def _context(self, organization_id="org-aaa", actor_id="user-ops-1"):
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

    def test_t1_create_happy_path_draft_with_computed_integer_cent_total(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        context = self._context()
        vendor = self._vendor(conn, context)
        bolt = self._part(conn, context, sku="bolt-m8", name="M8 bolt")
        nut = self._part(conn, context, sku="nut-m8", name="M8 nut")
        lines = [
            {"part_id": bolt["id"], "quantity": 3, "unit_cost_cents": 1250},
            {"part_id": nut["id"], "quantity": 2, "unit_cost_cents": 400},
        ]
        request = self._request(conn, context, vendor["id"], lines)
        self.assertTrue(request["id"].startswith("prq-"))
        self.assertEqual("draft", request["status"])
        self.assertEqual(3 * 1250 + 2 * 400, request["total_cents"])
        self.assertEqual(1, request["version"])
        self.assertIsNone(request["archived_at"])
        fetched = get_purchase_request(conn, context, request["id"])
        self.assertEqual(request["id"], fetched["id"])
        line_rows = list_request_lines(conn, context, purchase_request_id=request["id"])
        self.assertEqual(2, len(line_rows))
        for row in line_rows:
            self.assertTrue(row["id"].startswith("prl-"))
            self.assertIsNone(row["archived_at"])
        self.assertEqual(
            request["total_cents"],
            sum(row["quantity"] * row["unit_cost_cents"] for row in line_rows),
        )

    def test_t2_missing_and_cross_org_service_ids_not_found_nothing_stored(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        own = self._context()
        other = self._context("org-bbb")
        own_vendor = self._vendor(conn, own)
        foreign_vendor = self._vendor(conn, other, name="Foreign Vendor")
        bolt = self._part(conn, own, sku="bolt-m8", name="M8 bolt")
        foreign_part = self._part(conn, other, sku="bolt-m8", name="M8 bolt")
        lines = [{"part_id": bolt["id"], "quantity": 1, "unit_cost_cents": 100}]
        with self.assertRaises(NotFoundError) as missing_vendor:
            self._request(conn, own, "ven-does-not-exist", lines)
        with self.assertRaises(NotFoundError) as cross_vendor:
            self._request(conn, own, foreign_vendor["id"], lines)
        with self.assertRaises(NotFoundError) as missing_part:
            self._request(conn, own, own_vendor["id"], [
                {"part_id": "prt-does-not-exist", "quantity": 1, "unit_cost_cents": 100},
            ])
        with self.assertRaises(NotFoundError) as cross_part:
            self._request(conn, own, own_vendor["id"], [
                {"part_id": foreign_part["id"], "quantity": 1, "unit_cost_cents": 100},
            ])
        for caught in (missing_vendor, cross_vendor, missing_part, cross_part):
            self.assertEqual(REQUEST_NOT_FOUND_MESSAGE, str(caught.exception))
        self.assertEqual(
            0, conn.execute("SELECT COUNT(*) FROM purchase_requests").fetchone()[0],
        )
        self.assertEqual(
            0, conn.execute("SELECT COUNT(*) FROM purchase_request_lines").fetchone()[0],
        )

    def test_t3_floats_bools_and_bad_line_shapes_rejected_nothing_stored(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        context = self._context()
        vendor = self._vendor(conn, context)
        bolt = self._part(conn, context, sku="bolt-m8", name="M8 bolt")
        good = {"part_id": bolt["id"], "quantity": 1, "unit_cost_cents": 100}
        for bad in (
            {**good, "quantity": 2.5},
            {**good, "quantity": True},
            {**good, "quantity": 0},
            {**good, "quantity": -1},
            {**good, "unit_cost_cents": 10.5},
            {**good, "unit_cost_cents": False},
            {**good, "unit_cost_cents": -1},
        ):
            with self.assertRaises(ValidationError):
                self._request(conn, context, vendor["id"], [bad])
        with self.assertRaises(ValidationError):
            self._request(conn, context, vendor["id"], ["not-a-dict"])
        with self.assertRaises(ValidationError):
            create_purchase_request(
                conn, context, vendor_id=vendor["id"], lines=good, clock=self._tick_clock(),
            )
        self.assertEqual(
            0, conn.execute("SELECT COUNT(*) FROM purchase_requests").fetchone()[0],
        )
        self.assertEqual(
            0, conn.execute("SELECT COUNT(*) FROM purchase_request_lines").fetchone()[0],
        )

    def test_t4_archived_vendor_cannot_receive_purchase_request(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        context = self._context()
        vendor = self._vendor(conn, context)
        bolt = self._part(conn, context, sku="bolt-m8", name="M8 bolt")
        lines = [{"part_id": bolt["id"], "quantity": 1, "unit_cost_cents": 100}]
        with conn:
            conn.execute(
                "UPDATE vendors SET archived_at = ? WHERE id = ?",
                (format_rfc3339(datetime.now(timezone.utc)), vendor["id"]),
            )
        with self.assertRaises(ValidationError) as caught:
            self._request(conn, context, vendor["id"], lines)
        self.assertEqual(
            "archived vendors cannot receive purchase requests", str(caught.exception),
        )
        self.assertEqual(
            0, conn.execute("SELECT COUNT(*) FROM purchase_requests").fetchone()[0],
        )
        self.assertEqual(
            0, conn.execute("SELECT COUNT(*) FROM purchase_request_lines").fetchone()[0],
        )

    def test_t5_get_purchase_request_roundtrip_and_no_leak(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        own = self._context()
        vendor = self._vendor(conn, own)
        bolt = self._part(conn, own, sku="bolt-m8", name="M8 bolt")
        request = self._request(conn, own, vendor["id"], [
            {"part_id": bolt["id"], "quantity": 2, "unit_cost_cents": 500},
        ])
        fetched = get_purchase_request(conn, own, request["id"])
        self.assertEqual(request["id"], fetched["id"])
        with self.assertRaises(NotFoundError) as missing:
            get_purchase_request(conn, own, "prq-does-not-exist")
        with self.assertRaises(NotFoundError) as cross:
            get_purchase_request(conn, self._context("org-bbb"), request["id"])
        self.assertEqual(REQUEST_NOT_FOUND_MESSAGE, str(missing.exception))
        self.assertEqual(REQUEST_NOT_FOUND_MESSAGE, str(cross.exception))

    def test_t6_list_is_scoped_and_oldest_first(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        own = self._context()
        other = self._context("org-bbb")
        own_vendor = self._vendor(conn, own)
        other_vendor = self._vendor(conn, other, name="Foreign Vendor")
        bolt = self._part(conn, own, sku="bolt-m8", name="M8 bolt")
        other_bolt = self._part(conn, other, sku="bolt-m8", name="M8 bolt")
        own_lines = [{"part_id": bolt["id"], "quantity": 1, "unit_cost_cents": 100}]
        other_lines = [{"part_id": other_bolt["id"], "quantity": 1, "unit_cost_cents": 100}]
        first = self._request(conn, own, own_vendor["id"], own_lines)
        second = self._request(conn, own, own_vendor["id"], own_lines)
        self._request(conn, other, other_vendor["id"], other_lines)
        rows = list_purchase_requests(conn, own)
        self.assertEqual([first["id"], second["id"]], [row["id"] for row in rows])
        other_rows = list_purchase_requests(conn, other)
        self.assertEqual(1, len(other_rows))
        self.assertNotEqual(first["id"], other_rows[0]["id"])

    def test_t7_list_request_lines_returns_live_lines_only(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        own = self._context()
        vendor = self._vendor(conn, own)
        bolt = self._part(conn, own, sku="bolt-m8", name="M8 bolt")
        nut = self._part(conn, own, sku="nut-m8", name="M8 nut")
        request = self._request(conn, own, vendor["id"], [
            {"part_id": bolt["id"], "quantity": 2, "unit_cost_cents": 500},
            {"part_id": nut["id"], "quantity": 1, "unit_cost_cents": 200},
        ])
        line_rows = list_request_lines(conn, own, purchase_request_id=request["id"])
        self.assertEqual(2, len(line_rows))
        archived_id = line_rows[0]["id"]
        with conn:
            conn.execute(
                "UPDATE purchase_request_lines SET archived_at = ? WHERE id = ?",
                (format_rfc3339(datetime.now(timezone.utc)), archived_id),
            )
        live = list_request_lines(conn, own, purchase_request_id=request["id"])
        self.assertEqual(1, len(live))
        self.assertEqual(line_rows[1]["id"], live[0]["id"])
        self.assertIsNone(live[0]["archived_at"])
        with self.assertRaises(NotFoundError) as missing:
            list_request_lines(conn, own, purchase_request_id="prq-does-not-exist")
        with self.assertRaises(NotFoundError) as cross:
            list_request_lines(conn, self._context("org-bbb"), purchase_request_id=request["id"])
        self.assertEqual(REQUEST_NOT_FOUND_MESSAGE, str(missing.exception))
        self.assertEqual(REQUEST_NOT_FOUND_MESSAGE, str(cross.exception))

    def test_t8_request_total_cents_sums_live_line_totals(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        own = self._context()
        vendor = self._vendor(conn, own)
        bolt = self._part(conn, own, sku="bolt-m8", name="M8 bolt")
        nut = self._part(conn, own, sku="nut-m8", name="M8 nut")
        request = self._request(conn, own, vendor["id"], [
            {"part_id": bolt["id"], "quantity": 2, "unit_cost_cents": 500},
            {"part_id": nut["id"], "quantity": 3, "unit_cost_cents": 200},
        ])
        self.assertEqual(
            2 * 500 + 3 * 200,
            request_total_cents(conn, own, purchase_request_id=request["id"]),
        )
        self.assertEqual(
            request["total_cents"],
            request_total_cents(conn, own, purchase_request_id=request["id"]),
        )


if __name__ == "__main__":
    unittest.main()
