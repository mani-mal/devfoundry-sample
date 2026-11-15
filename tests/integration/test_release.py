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
