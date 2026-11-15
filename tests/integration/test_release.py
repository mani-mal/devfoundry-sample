"""Integration tests (T036, M5): reservation release and consumption.

Applies the REAL shipped migrations to a temporary file database and
exercises release/consume through public service functions only.
Acceptance (spec M5/T036): quantities cannot be reused or exceed the
reservation — a released/consumed reservation cannot be released or
consumed again; every write respects remaining_quantity; the ledger
records the exact deltas.
"""

import tempfile
import unittest
from datetime import datetime, timezone

from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError
from opsledger.core.migrations import migrate
from opsledger.assets import create_site, create_asset
from opsledger.workorders import create_work_order
from opsledger.parts import create_part, create_stock_location
from opsledger.inventory import adjust_stock, list_movements, reserve_stock
from opsledger.inventory import consume_reservation, release_reservation


class ReleaseConsumeTest(unittest.TestCase):
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

    def _context(self, organization_id="org-aaa", actor_id="user-111"):
        return OrganizationContext(organization_id=organization_id, actor_id=actor_id)

    def _tick_clock(self):
        self._tick = getattr(self, "_tick", 0) + 1
        return FixedClock(datetime(2026, 11, 13, 12, self._tick, 0, tzinfo=timezone.utc))

    def _seed_fixture(self, conn, context, opening=10, reserved_quantity=4):
        """Part/location with an opening adjustment, work order, one reservation."""
        self._seed_organizations(conn)
        part = create_part(
            conn, context, sku="bolt-m8", name="M8 bolt", unit_of_measure="unit",
            standard_cost_cents=2500, clock=self._tick_clock(),
        )
        location = create_stock_location(conn, context, code="main", name="Main store", clock=self._tick_clock())
        site = create_site(conn, context, code="main", name="Site A", clock=self._tick_clock())
        asset = create_asset(
            conn, context, site_id=site["id"], tag="pump-001", name="Asset pump-001",
            criticality="medium", purchase_cost_cents=10000, clock=self._tick_clock(),
        )
        work_order = create_work_order(
            conn, context, site_id=site["id"], asset_id=asset["id"], number="wo-100",
            title="Rebuild pump", description="Full rebuild", priority="high",
            requester_id="user-111", clock=self._tick_clock(),
        )
        balance = adjust_stock(
            conn, context, part_id=part["id"], location_id=location["id"],
            quantity_delta=opening, reason="opening", expected_version=1,
            actor_id=context.actor_id, clock=self._tick_clock(),
        )
        reservation = reserve_stock(
            conn, context, part_id=part["id"], location_id=location["id"],
            work_order_id=work_order["id"], quantity=reserved_quantity,
            expected_version=balance["version"], actor_id=context.actor_id,
            clock=self._tick_clock(),
        )
        return part, location, work_order, balance, reservation

    def _reserve(self, conn, context, part, location, work_order, balance, quantity):
        return reserve_stock(
            conn, context, part_id=part["id"], location_id=location["id"],
            work_order_id=work_order["id"], quantity=quantity,
            expected_version=balance["version"], actor_id=context.actor_id,
            clock=self._tick_clock(),
        )

    def _movements(self, conn, context, part, location):
        return list_movements(conn, context, part_id=part["id"], location_id=location["id"])

    def test_t1_partial_release_keeps_reservation_active(self):
        conn = self._open_migrated()
        context = self._context()
        part, location, work_order, balance, reservation = self._seed_fixture(conn, context)
        released = release_reservation(
            conn, context, reservation_id=reservation["id"], quantity=3,
            expected_version=balance["version"] + 1, actor_id=context.actor_id,
            clock=self._tick_clock(),
        )
        self.assertEqual("active", released["status"])
        self.assertEqual(1, released["remaining_quantity"])
        movements = self._movements(conn, context, part, location)
        self.assertEqual("release", movements[-1]["operation"])
        self.assertEqual((0, -3), (movements[-1]["on_hand_delta"], movements[-1]["reserved_delta"]))
        balance_after = conn.execute(
            "SELECT * FROM stock_balances WHERE id = ?", (balance["id"],)
        ).fetchone()
        self.assertEqual((10, 1, 4), (balance_after["on_hand"], balance_after["reserved"], balance_after["version"]))

    def test_t2_full_release_marks_released_and_blocks_reuse(self):
        conn = self._open_migrated()
        context = self._context()
        part, location, work_order, balance, reservation = self._seed_fixture(conn, context)
        released = release_reservation(
            conn, context, reservation_id=reservation["id"], quantity=4,
            expected_version=balance["version"] + 1, actor_id=context.actor_id,
            clock=self._tick_clock(),
        )
        self.assertEqual("released", released["status"])
        self.assertEqual(0, released["remaining_quantity"])
        with self.assertRaises(ConflictError) as caught:
            release_reservation(
                conn, context, reservation_id=reservation["id"], quantity=1,
                expected_version=balance["version"] + 2, actor_id=context.actor_id,
                clock=self._tick_clock(),
            )
        self.assertEqual("reservation is not active", str(caught.exception))
        with self.assertRaises(ConflictError):
            consume_reservation(
                conn, context, reservation_id=reservation["id"], quantity=1,
                expected_version=balance["version"] + 2, actor_id=context.actor_id,
                clock=self._tick_clock(),
            )
        movements = self._movements(conn, context, part, location)
        self.assertEqual(3, len(movements))
        self.assertEqual(("adjust", "reserve", "release"), tuple(m["operation"] for m in movements))

    def test_t3_partial_consume_drops_on_hand_and_reserved(self):
        conn = self._open_migrated()
        context = self._context()
        part, location, work_order, balance, reservation = self._seed_fixture(conn, context)
        consumed = consume_reservation(
            conn, context, reservation_id=reservation["id"], quantity=1,
            expected_version=balance["version"] + 1, actor_id=context.actor_id,
            clock=self._tick_clock(),
        )
        self.assertEqual("active", consumed["status"])
        self.assertEqual(3, consumed["remaining_quantity"])
        movements = self._movements(conn, context, part, location)
        self.assertEqual("consume", movements[-1]["operation"])
        self.assertEqual((-1, -1), (movements[-1]["on_hand_delta"], movements[-1]["reserved_delta"]))
        balance_after = conn.execute(
            "SELECT * FROM stock_balances WHERE id = ?", (balance["id"],)
        ).fetchone()
        self.assertEqual((9, 3, 4), (balance_after["on_hand"], balance_after["reserved"], balance_after["version"]))

    def test_t4_full_consume_marks_consumed_and_blocks_reuse(self):
        conn = self._open_migrated()
        context = self._context()
        part, location, work_order, balance, reservation = self._seed_fixture(conn, context)
        consumed = consume_reservation(
            conn, context, reservation_id=reservation["id"], quantity=4,
            expected_version=balance["version"] + 1, actor_id=context.actor_id,
            clock=self._tick_clock(),
        )
        self.assertEqual("consumed", consumed["status"])
        self.assertEqual(0, consumed["remaining_quantity"])
        with self.assertRaises(ConflictError) as caught:
            consume_reservation(
                conn, context, reservation_id=reservation["id"], quantity=1,
                expected_version=balance["version"] + 2, actor_id=context.actor_id,
                clock=self._tick_clock(),
            )
        self.assertEqual("reservation is not active", str(caught.exception))
        balance_after = conn.execute(
            "SELECT * FROM stock_balances WHERE id = ?", (balance["id"],)
        ).fetchone()
        self.assertEqual((6, 0, 4), (balance_after["on_hand"], balance_after["reserved"], balance_after["version"]))

    def test_t5_release_and_consume_cannot_exceed_remaining(self):
        conn = self._open_migrated()
        context = self._context()
        part, location, work_order, balance, reservation = self._seed_fixture(conn, context, reserved_quantity=2)
        with self.assertRaises(ConflictError) as release_caught:
            release_reservation(
                conn, context, reservation_id=reservation["id"], quantity=3,
                expected_version=balance["version"] + 1, actor_id=context.actor_id,
                clock=self._tick_clock(),
            )
        self.assertEqual("release exceeds remaining reservation quantity", str(release_caught.exception))
        with self.assertRaises(ConflictError) as consume_caught:
            consume_reservation(
                conn, context, reservation_id=reservation["id"], quantity=3,
                expected_version=balance["version"] + 1, actor_id=context.actor_id,
                clock=self._tick_clock(),
            )
        self.assertEqual("consumption exceeds remaining reservation quantity", str(consume_caught.exception))
        reservation_after = conn.execute(
            "SELECT * FROM reservations WHERE id = ?", (reservation["id"],)
        ).fetchone()
        self.assertEqual((2, "active"), (reservation_after["remaining_quantity"], reservation_after["status"]))
        movements = self._movements(conn, context, part, location)
        self.assertEqual(2, len(movements))

    def test_t6_quantity_validation_and_unknown_reservation(self):
        conn = self._open_migrated()
        context = self._context()
        part, location, work_order, balance, reservation = self._seed_fixture(conn, context)
        for quantity in (0, -1, 2.5, "2", True):
            with self.assertRaises(ValidationError):
                release_reservation(
                    conn, context, reservation_id=reservation["id"], quantity=quantity,
                    expected_version=balance["version"] + 1, actor_id=context.actor_id,
                    clock=self._tick_clock(),
                )
            with self.assertRaises(ValidationError):
                consume_reservation(
                    conn, context, reservation_id=reservation["id"], quantity=quantity,
                    expected_version=balance["version"] + 1, actor_id=context.actor_id,
                    clock=self._tick_clock(),
                )
        with self.assertRaises(NotFoundError):
            release_reservation(
                conn, context, reservation_id="rsv-does-not-exist", quantity=1,
                expected_version=balance["version"] + 1, actor_id=context.actor_id,
                clock=self._tick_clock(),
            )

    def test_t7_cross_organization_reservation_is_invisible(self):
        conn = self._open_migrated()
        context = self._context()
        part, location, work_order, balance, reservation = self._seed_fixture(conn, context)
        other_context = self._context("org-bbb")
        with self.assertRaises(NotFoundError):
            release_reservation(
                conn, other_context, reservation_id=reservation["id"], quantity=1,
                expected_version=balance["version"] + 1, actor_id=other_context.actor_id,
                clock=self._tick_clock(),
            )
        with self.assertRaises(NotFoundError):
            consume_reservation(
                conn, other_context, reservation_id=reservation["id"], quantity=1,
                expected_version=balance["version"] + 1, actor_id=other_context.actor_id,
                clock=self._tick_clock(),
            )
        reservation_after = conn.execute(
            "SELECT * FROM reservations WHERE id = ?", (reservation["id"],)
        ).fetchone()
        self.assertEqual((4, "active"), (reservation_after["remaining_quantity"], reservation_after["status"]))

    def test_t8_stale_version_conflict(self):
        conn = self._open_migrated()
        context = self._context()
        part, location, work_order, balance, reservation = self._seed_fixture(conn, context)
        with self.assertRaises(ConflictError):
            release_reservation(
                conn, context, reservation_id=reservation["id"], quantity=1,
                expected_version=1, actor_id=context.actor_id,
                clock=self._tick_clock(),
            )
        with self.assertRaises(ConflictError):
            consume_reservation(
                conn, context, reservation_id=reservation["id"], quantity=1,
                expected_version=1, actor_id=context.actor_id,
                clock=self._tick_clock(),
            )
        reservation_after = conn.execute(
            "SELECT * FROM reservations WHERE id = ?", (reservation["id"],)
        ).fetchone()
        self.assertEqual((4, "active"), (reservation_after["remaining_quantity"], reservation_after["status"]))


if __name__ == "__main__":
    unittest.main()
