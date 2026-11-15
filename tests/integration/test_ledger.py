"""Integration tests (T034, M5): balance and movement ledger, opening adjustment.

Applies the REAL shipped migrations to a temporary file database and
exercises the ledger through public service functions only. Acceptance
(spec M5/T034): reconciliation matches the movement sum; reason required;
a refused adjustment stores nothing; movements are immutable.
"""

import tempfile
import unittest
from datetime import datetime, timezone

from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect
from opsledger.core.errors import ConflictError, ValidationError
from opsledger.core.migrations import migrate
from opsledger.parts import create_part, create_stock_location
from opsledger.inventory import (
    INSUFFICIENT_STOCK_MESSAGE,
    REASON_REQUIRED_MESSAGE,
    adjust_stock,
    get_balance,
    get_or_create_balance,
    list_balances,
    list_movements,
    reconcile_balance,
)


class LedgerTest(unittest.TestCase):
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

    def _clock(self):
        return FixedClock(datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc))

    def _seed_part_and_location(self, conn, context):
        self._seed_organizations(conn)
        self._tick = getattr(self, "_tick", 0) + 1
        tick_clock = FixedClock(datetime(2026, 11, 13, 12, self._tick, 0, tzinfo=timezone.utc))
        part = create_part(
            conn, context, sku="bolt-m8", name="M8 bolt", unit_of_measure="unit",
            standard_cost_cents=2500, clock=tick_clock,
        )
        self._tick += 1
        tick_clock = FixedClock(datetime(2026, 11, 13, 12, self._tick, 0, tzinfo=timezone.utc))
        location = create_stock_location(conn, context, code="main", name="Main store", clock=tick_clock)
        return part, location

    def _adjust(self, conn, context, part, location, delta, reason="opening", version=None):
        balance = get_or_create_balance(conn, context, part_id=part["id"], location_id=location["id"], clock=self._clock())
        self._tick = getattr(self, "_tick", 0) + 1
        tick_clock = FixedClock(datetime(2026, 11, 13, 12, self._tick, 0, tzinfo=timezone.utc))
        return adjust_stock(
            conn, context, part_id=part["id"], location_id=location["id"],
            quantity_delta=delta, reason=reason,
            expected_version=version if version is not None else balance["version"],
            actor_id=context.actor_id, clock=tick_clock,
        )

    def test_t1_opening_adjustment_creates_balance_and_movement(self):
        conn = self._open_migrated()
        part, location = self._seed_part_and_location(conn, self._context())
        balance = self._adjust(conn, self._context(), part, location, 10)
        self.assertEqual(10, balance["on_hand"])
        self.assertEqual(0, balance["reserved"])
        self.assertEqual(2, balance["version"])
        movements = list_movements(conn, self._context(), part_id=part["id"], location_id=location["id"])
        self.assertEqual(1, len(movements))
        self.assertEqual("adjust", movements[0]["operation"])
        self.assertEqual(10, movements[0]["on_hand_delta"])
        self.assertEqual(0, movements[0]["reserved_delta"])
        self.assertEqual("opening", movements[0]["reason"])

    def test_t2_reconciliation_matches_movement_sum(self):
        conn = self._open_migrated()
        part, location = self._seed_part_and_location(conn, self._context())
        self._adjust(conn, self._context(), part, location, 10)
        self._adjust(conn, self._context(), part, location, -3, reason="shrinkage")
        report = reconcile_balance(conn, self._context(), part_id=part["id"], location_id=location["id"], clock=self._clock())
        self.assertEqual(7, report["on_hand_sum"])
        self.assertEqual(7, report["balance"]["on_hand"])
        self.assertEqual(True, report["matches"])

    def test_t3_reason_required_refused_adjustment_stores_nothing(self):
        conn = self._open_migrated()
        part, location = self._seed_part_and_location(conn, self._context())
        for reason in (None, "", "   "):
            with self.assertRaises(ValidationError) as caught:
                self._adjust(conn, self._context(), part, location, 10, reason=reason)
            self.assertEqual(REASON_REQUIRED_MESSAGE, str(caught.exception))
        balances = list_balances(conn, self._context())
        self.assertEqual(1, len(balances))
        self.assertEqual(0, balances[0]["on_hand"])
        self.assertEqual(1, balances[0]["version"])

    def test_t4_on_hand_cannot_fall_below_reserved_or_zero(self):
        conn = self._open_migrated()
        part, location = self._seed_part_and_location(conn, self._context())
        self._adjust(conn, self._context(), part, location, 10)
        with self.assertRaises(ConflictError) as caught:
            self._adjust(conn, self._context(), part, location, -11)
        self.assertEqual(INSUFFICIENT_STOCK_MESSAGE, str(caught.exception))
        balance = get_balance(conn, self._context(), get_or_create_balance(conn, self._context(), part_id=part["id"], location_id=location["id"], clock=self._clock())["id"])
        self.assertEqual(10, balance["on_hand"])
        self.assertEqual(2, balance["version"])
        movements = list_movements(conn, self._context(), part_id=part["id"], location_id=location["id"])
        self.assertEqual(1, len(movements))

    def test_t5_stale_version_conflict(self):
        conn = self._open_migrated()
        part, location = self._seed_part_and_location(conn, self._context())
        self._adjust(conn, self._context(), part, location, 10)
        with self.assertRaises(ConflictError):
            self._adjust(conn, self._context(), part, location, 5, version=1)

    def test_t6_movements_are_immutable_ledger_is_accounting_source(self):
        conn = self._open_migrated()
        part, location = self._seed_part_and_location(conn, self._context())
        self._adjust(conn, self._context(), part, location, 10)
        self._adjust(conn, self._context(), part, location, -4, reason="correction")
        movements = list_movements(conn, self._context(), part_id=part["id"], location_id=location["id"])
        self.assertEqual(2, len(movements))
        self.assertEqual(10, movements[0]["on_hand_delta"])
        self.assertEqual(-4, movements[1]["on_hand_delta"])
        report = reconcile_balance(conn, self._context(), part_id=part["id"], location_id=location["id"], clock=self._clock())
        self.assertEqual(True, report["matches"])

    def test_t7_cross_organization_balance_is_invisible(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        self._tick = getattr(self, "_tick", 0) + 1
        part = create_part(
            conn, self._context(), sku="bolt-m8", name="M8 bolt", unit_of_measure="unit",
            standard_cost_cents=2500,
            clock=FixedClock(datetime(2026, 11, 13, 12, self._tick, 0, tzinfo=timezone.utc)),
        )
        self._tick += 1
        location = create_stock_location(
            conn, self._context(), code="main", name="Main store",
            clock=FixedClock(datetime(2026, 11, 13, 12, self._tick, 0, tzinfo=timezone.utc)),
        )
        self._adjust(conn, self._context(), part, location, 10)
        own = list_balances(conn, self._context())
        self.assertEqual(1, len(own))
        other_context = self._context("org-bbb")
        self._tick += 1
        other_part = create_part(
            conn, other_context, sku="bolt-m8", name="M8 bolt", unit_of_measure="unit",
            standard_cost_cents=2500,
            clock=FixedClock(datetime(2026, 11, 13, 12, self._tick, 0, tzinfo=timezone.utc)),
        )
        self._tick += 1
        other_location = create_stock_location(
            conn, other_context, code="main", name="Main store",
            clock=FixedClock(datetime(2026, 11, 13, 12, self._tick, 0, tzinfo=timezone.utc)),
        )
        self._adjust(conn, other_context, other_part, other_location, 5)
        other_balances = list_balances(conn, other_context)
        self.assertEqual(1, len(other_balances))
        self.assertNotEqual(own[0]["id"], other_balances[0]["id"])
        self.assertEqual(
            1, len(list_movements(conn, self._context(), part_id=part["id"], location_id=location["id"])),
        )
        self.assertEqual(
            1, len(list_movements(conn, other_context, part_id=other_part["id"], location_id=other_location["id"])),
        )

    def test_t8_negative_and_zero_deltas_refused(self):
        conn = self._open_migrated()
        part, location = self._seed_part_and_location(conn, self._context())
        for delta in (0, 1.5, "10", True):
            with self.assertRaises(ValidationError):
                adjust_stock(
                    conn, self._context(), part_id=part["id"], location_id=location["id"],
                    quantity_delta=delta, reason="x", expected_version=1,
                    actor_id="user-111", clock=self._clock(),
                )
        balances = list_balances(conn, self._context())
        self.assertEqual(0, len(balances))


if __name__ == "__main__":
    unittest.main()
