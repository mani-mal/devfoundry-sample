"""Integration tests (T035, M5): transactional reservation service.

Applies the REAL shipped migrations to a temporary file database and
exercises reservations through public service functions only. Acceptance
(spec M5/T035): insufficient stock changes nothing — a refused reservation
leaves the balance, the movement ledger, and the reservations table
untouched; the atomic conditional UPDATE makes concurrent overselling
impossible.
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


class ReservationTest(unittest.TestCase):
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

    def _seed_fixture(self, conn, context, opening=10):
        """One part/location with an opening adjustment and one work order."""
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
        return part, location, work_order, balance

    def _movements(self, conn, context, part, location):
        return list_movements(conn, context, part_id=part["id"], location_id=location["id"])

    def test_t1_reserve_creates_active_reservation_and_movement(self):
        conn = self._open_migrated()
        context = self._context()
        part, location, work_order, balance = self._seed_fixture(conn, context)
        reservation = reserve_stock(
            conn, context, part_id=part["id"], location_id=location["id"],
            work_order_id=work_order["id"], quantity=3,
            expected_version=balance["version"], actor_id=context.actor_id,
            clock=self._tick_clock(),
        )
        self.assertEqual("active", reservation["status"])
        self.assertEqual(3, reservation["quantity"])
        self.assertEqual(3, reservation["remaining_quantity"])
        balance_after = conn.execute(
            "SELECT * FROM stock_balances WHERE id = ?", (balance["id"],)
        ).fetchone()
        self.assertEqual(10, balance_after["on_hand"])
        self.assertEqual(3, balance_after["reserved"])
        self.assertEqual(3, balance_after["version"])
        movements = self._movements(conn, context, part, location)
        self.assertEqual(2, len(movements))
        self.assertEqual(("adjust", "reserve"), (movements[0]["operation"], movements[1]["operation"]))
        self.assertEqual((0, 3), (movements[1]["on_hand_delta"], movements[1]["reserved_delta"]))
        self.assertEqual(work_order["id"], movements[1]["work_order_id"])

    def test_t2_insufficient_stock_changes_nothing(self):
        conn = self._open_migrated()
        context = self._context()
        part, location, work_order, balance = self._seed_fixture(conn, context, opening=5)
        before_movements = self._movements(conn, context, part, location)
        with self.assertRaises(ConflictError) as caught:
            reserve_stock(
                conn, context, part_id=part["id"], location_id=location["id"],
                work_order_id=work_order["id"], quantity=6,
                expected_version=balance["version"], actor_id=context.actor_id,
                clock=self._tick_clock(),
            )
        self.assertEqual("reservation exceeds available stock", str(caught.exception))
        after_balance = conn.execute(
            "SELECT * FROM stock_balances WHERE id = ?", (balance["id"],)
        ).fetchone()
        self.assertEqual((5, 0, 2), (after_balance["on_hand"], after_balance["reserved"], after_balance["version"]))
        self.assertEqual(len(before_movements), len(self._movements(conn, context, part, location)))
        count = conn.execute("SELECT COUNT(*) FROM reservations").fetchone()
        self.assertEqual(0, count[0])
