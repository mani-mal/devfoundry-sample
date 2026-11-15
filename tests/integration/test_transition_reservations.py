"""Integration tests (T038, M5): work-order transitions × reservations.

Applies the REAL shipped migrations to a temporary file database and
exercises the reservation-aware transition service through public
service functions only. Acceptance (spec M5/T038): cancel releases
reservations atomically; completion refuses outstanding reservations;
state and history unchanged on refusal (APP08).
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
from opsledger.workorders.orders import create_work_order
from opsledger.workorders.transitions import transition_work_order
from opsledger.workorders.reservation_rules import transition_work_order_with_reservations
from opsledger.parts import create_part, create_stock_location
from opsledger.inventory import adjust_stock, list_movements, reserve_stock


class TransitionReservationsTest(unittest.TestCase):
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
        """Part/location + site/asset + work order + opening + one reservation."""
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

    def _movements(self, conn, context, part, location):
        return list_movements(conn, context, part_id=part["id"], location_id=location["id"])

    def test_t1_cancel_releases_outstanding_reservation_atomically(self):
        conn = self._open_migrated()
        context = self._context()
        part, location, work_order, balance, reservation = self._seed_fixture(conn, context)
        cancelled = transition_work_order_with_reservations(
            conn, context, work_order_id=work_order["id"], to_status="cancelled",
            expected_version=work_order["version"], reason="no longer needed",
            actor_id=context.actor_id, clock=self._tick_clock(),
        )
        self.assertEqual("cancelled", cancelled["status"])
        self.assertEqual(work_order["version"] + 1, cancelled["version"])
        after = conn.execute(
            "SELECT * FROM reservations WHERE id = ?", (reservation["id"],)
        ).fetchone()
        self.assertEqual(("released", 0), (after["status"], after["remaining_quantity"]))
        balance_after = conn.execute(
            "SELECT * FROM stock_balances WHERE id = ?", (balance["id"],)
        ).fetchone()
        self.assertEqual((10, 0, 4), (balance_after["on_hand"], balance_after["reserved"], balance_after["version"]))
        movements = self._movements(conn, context, part, location)
        self.assertEqual(("adjust", "reserve", "release"), tuple(m["operation"] for m in movements))
        self.assertEqual((0, -4), (movements[-1]["on_hand_delta"], movements[-1]["reserved_delta"]))
        events = conn.execute(
            "SELECT * FROM work_order_events WHERE work_order_id = ? ORDER BY created_at, id",
            (work_order["id"],),
        ).fetchall()
        self.assertEqual(1, len(events))
        self.assertEqual(("open", "cancelled"), (events[0]["from_status"], events[0]["to_status"]))
        audits = conn.execute(
            "SELECT * FROM audit_events WHERE entity_id = ? AND entity_type = 'work_order'",
            (work_order["id"],),
        ).fetchall()
        self.assertEqual(1, len(audits))

    def test_t2_completion_refuses_outstanding_reservation(self):
        conn = self._open_migrated()
        context = self._context()
        part, location, work_order, balance, reservation = self._seed_fixture(conn, context)
        started = transition_work_order(
            conn, context, work_order_id=work_order["id"], to_status="assigned",
            expected_version=work_order["version"], reason=None,
            actor_id=context.actor_id, clock=self._tick_clock(),
        )
        in_progress = transition_work_order(
            conn, context, work_order_id=work_order["id"], to_status="in_progress",
            expected_version=started["version"], reason=None,
            actor_id=context.actor_id, clock=self._tick_clock(),
        )
        with self.assertRaises(ConflictError) as caught:
            transition_work_order_with_reservations(
                conn, context, work_order_id=work_order["id"], to_status="completed",
                expected_version=in_progress["version"], reason=None,
                actor_id=context.actor_id, clock=self._tick_clock(),
            )
        self.assertEqual(
            "work order has outstanding reservations; release or consume them first",
            str(caught.exception),
        )
        after = conn.execute(
            "SELECT * FROM work_orders WHERE id = ?", (work_order["id"],)
        ).fetchone()
        self.assertEqual(("in_progress", in_progress["version"]), (after["status"], after["version"]))
        events = conn.execute(
            "SELECT * FROM work_order_events WHERE work_order_id = ?", (work_order["id"],)
        ).fetchall()
        self.assertEqual(2, len(events))
        reservation_after = conn.execute(
            "SELECT * FROM reservations WHERE id = ?", (reservation["id"],)
        ).fetchone()
        self.assertEqual(("active", 4), (reservation_after["status"], reservation_after["remaining_quantity"]))

    def test_t3_completion_succeeds_after_release(self):
        conn = self._open_migrated()
        context = self._context()
        part, location, work_order, balance, reservation = self._seed_fixture(conn, context)
        started = transition_work_order(
            conn, context, work_order_id=work_order["id"], to_status="assigned",
            expected_version=work_order["version"], reason=None,
            actor_id=context.actor_id, clock=self._tick_clock(),
        )
        in_progress = transition_work_order(
            conn, context, work_order_id=work_order["id"], to_status="in_progress",
            expected_version=started["version"], reason=None,
            actor_id=context.actor_id, clock=self._tick_clock(),
        )
        from opsledger.inventory import release_reservation
        release_reservation(
            conn, context, reservation_id=reservation["id"], quantity=4,
            expected_version=balance["version"] + 1, actor_id=context.actor_id,
            clock=self._tick_clock(),
        )
        completed = transition_work_order_with_reservations(
            conn, context, work_order_id=work_order["id"], to_status="completed",
            expected_version=in_progress["version"], reason=None,
            actor_id=context.actor_id, clock=self._tick_clock(),
        )
        self.assertEqual("completed", completed["status"])
        self.assertEqual(in_progress["version"] + 1, completed["version"])

    def test_t4_completion_succeeds_after_consume(self):
        conn = self._open_migrated()
        context = self._context()
        part, location, work_order, balance, reservation = self._seed_fixture(conn, context)
        started = transition_work_order(
            conn, context, work_order_id=work_order["id"], to_status="assigned",
            expected_version=work_order["version"], reason=None,
            actor_id=context.actor_id, clock=self._tick_clock(),
        )
        in_progress = transition_work_order(
            conn, context, work_order_id=work_order["id"], to_status="in_progress",
            expected_version=started["version"], reason=None,
            actor_id=context.actor_id, clock=self._tick_clock(),
        )
        from opsledger.inventory import consume_reservation
        consume_reservation(
            conn, context, reservation_id=reservation["id"], quantity=4,
            expected_version=balance["version"] + 1, actor_id=context.actor_id,
            clock=self._tick_clock(),
        )
        completed = transition_work_order_with_reservations(
            conn, context, work_order_id=work_order["id"], to_status="completed",
            expected_version=in_progress["version"], reason=None,
            actor_id=context.actor_id, clock=self._tick_clock(),
        )
        self.assertEqual("completed", completed["status"])
        movements = self._movements(conn, context, part, location)
        self.assertEqual(("adjust", "reserve", "consume"), tuple(m["operation"] for m in movements))

    def test_t5_no_reservation_completion_still_works(self):
        conn = self._open_migrated()
        context = self._context()
        part, location, work_order, balance, reservation = self._seed_fixture(conn, context)
        plain = create_work_order(
            conn, context, site_id=conn.execute("SELECT id FROM sites").fetchone()["id"],
            asset_id=conn.execute("SELECT id FROM assets").fetchone()["id"], number="wo-101",
            title="Oil change", description="Routine", priority="low",
            requester_id="user-111", clock=self._tick_clock(),
        )
        completed = transition_work_order_with_reservations(
            conn, context, work_order_id=plain["id"], to_status="cancelled",
            expected_version=plain["version"], reason="not needed",
            actor_id=context.actor_id, clock=self._tick_clock(),
        )
        self.assertEqual("cancelled", completed["status"])
        count = conn.execute("SELECT COUNT(*) FROM stock_movements WHERE work_order_id = ?", (plain["id"],)).fetchone()[0]
        self.assertEqual(0, count)
