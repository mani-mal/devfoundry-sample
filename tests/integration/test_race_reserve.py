"""Integration tests (T040, M5): competing reservations never oversell.

Spec §11.3 (the oracle): two independent SQLite connections reserve the
last available unit; at most one reservation may succeed and persisted
balances must remain valid. The test uses two independent connections
(created per thread, never shared) and a threading.Barrier; no
process-local lock is involved -- correctness comes from the atomic
conditional UPDATE inside one IMMEDIATE transaction. An independent
connection reconciles balances against the movement sum after both
workers finish.
"""

import tempfile
import threading
import unittest
from datetime import datetime, timezone

from opsledger.assets import create_asset, create_site
from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect
from opsledger.core.errors import ConflictError
from opsledger.core.migrations import migrate
from opsledger.inventory import adjust_stock, reconcile_balance, reserve_stock
from opsledger.parts import create_part, create_stock_location
from opsledger.workorders.orders import create_work_order


class RaceReserveLastUnitTest(unittest.TestCase):
    def _open_migrated(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db_path = tmp.name
        self.addCleanup(lambda: connect(tmp.name).close())
        conn = connect(tmp.name)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def _seed_fixture(self, conn, context, opening=1):
        """Part/location + site/asset + two work orders + opening adjustment."""
        created_text = "2026-11-06T12:00:00Z"
        with conn:
            conn.execute(
                "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                ("org-aaa", "org-aaa", "Organization AAA", created_text),
            )
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
        work_order_a = create_work_order(
            conn, context, site_id=site["id"], asset_id=asset["id"], number="wo-200",
            title="Race A", description="First racer", priority="high",
            requester_id="user-111", clock=self._tick_clock(),
        )
        work_order_b = create_work_order(
            conn, context, site_id=site["id"], asset_id=asset["id"], number="wo-201",
            title="Race B", description="Second racer", priority="high",
            requester_id="user-111", clock=self._tick_clock(),
        )
        balance = adjust_stock(
            conn, context, part_id=part["id"], location_id=location["id"],
            quantity_delta=opening, reason="opening", expected_version=1,
            actor_id=context.actor_id, clock=self._tick_clock(),
        )
        return part, location, work_order_a, work_order_b, balance

    def _tick_clock(self):
        self._tick = getattr(self, "_tick", 0) + 1
        return FixedClock(datetime(2026, 11, 13, 12, self._tick, 0, tzinfo=timezone.utc))

    def _count_active_reservations(self, conn):
        return conn.execute(
            "SELECT COUNT(*) FROM reservations WHERE status = 'active'"
        ).fetchone()[0]
