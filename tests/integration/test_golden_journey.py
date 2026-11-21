"""T077 part 1: golden journey regression, steps 1-4 of the 12-step journey.

Seeds the shared fixture (users, orgs, sites, memberships), creates one
work order, verifies the assignment denial for a user without site access,
assigns a real technician, moves the WO to in_progress, opens stock with
one adjustment, and verifies the insufficient-stock reservation refusal
leaves the balance unchanged. Parts 2 and 3 add methods to this class.
"""

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from opsledger.assets import create_asset, create_site
from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect, transaction
from opsledger.core.errors import ConflictError, PermissionDeniedError
from opsledger.core.migrations import migrate
from opsledger.inventory import adjust_stock, reserve_stock
from opsledger.parts import create_part, create_stock_location
from opsledger.workorders import assign_technician, create_work_order
from opsledger.workorders.transitions import transition_work_order


def _at(seconds: int) -> FixedClock:
    return FixedClock(
        datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    )


class GoldenJourneyTests(unittest.TestCase):
    def _open_migrated(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda p=tmp.name: os.path.exists(p) and os.unlink(p))
        self.addCleanup(lambda: connect(tmp.name).close())
        conn = connect(tmp.name)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def _seed_steps_1_to_4(self, conn):
        with transaction(conn) as tx:
            tx.execute(
                "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                ("org-a", "org-a", "Org A", "2026-11-06T12:00:00Z"),
            )
            tx.execute(
                "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                ("org-b", "org-b", "Org B", "2026-11-06T12:00:00Z"),
            )
            tx.execute(
                "INSERT INTO users (id, email, display_name, created_at) VALUES (?, ?, ?, ?)",
                ("usr-sup", "usr-sup@example.com", "Sup", "2026-11-06T12:00:00Z"),
            )
            tx.execute(
                "INSERT INTO users (id, email, display_name, created_at) VALUES (?, ?, ?, ?)",
                ("usr-tech", "usr-tech@example.com", "Tech", "2026-11-06T12:00:00Z"),
            )
            tx.execute(
                "INSERT INTO users (id, email, display_name, created_at) VALUES (?, ?, ?, ?)",
                ("usr-purch", "usr-purch@example.com", "Purch", "2026-11-06T12:00:00Z"),
            )
            tx.execute(
                "INSERT INTO users (id, email, display_name, created_at) VALUES (?, ?, ?, ?)",
                ("usr-appr", "usr-appr@example.com", "Appr", "2026-11-06T12:00:00Z"),
            )
            tx.execute(
                "INSERT INTO users (id, email, display_name, created_at) VALUES (?, ?, ?, ?)",
                ("usr-orgb", "usr-orgb@example.com", "OrgB", "2026-11-06T12:00:00Z"),
            )
            tx.execute(
                "INSERT INTO memberships (organization_id, user_id, role, created_at)"
                " VALUES (?, ?, ?, ?)",
                ("org-a", "usr-purch", "purchasing", "2026-11-06T12:00:00Z"),
            )
            tx.execute(
                "INSERT INTO memberships (organization_id, user_id, role, created_at)"
                " VALUES (?, ?, ?, ?)",
                ("org-a", "usr-appr", "approver", "2026-11-06T12:00:00Z"),
            )
        sup = OrganizationContext(organization_id="org-a", actor_id="usr-sup")
        site1 = create_site(conn, sup, code="site-1", name="Site One", clock=_at(10))
        site2 = create_site(conn, sup, code="site-2", name="Site Two", clock=_at(11))
        with transaction(conn) as tx:
            tx.execute(
                "INSERT INTO site_memberships"
                " (organization_id, site_id, user_id, granted_at, revoked_at)"
                " VALUES (?, ?, ?, ?, NULL)",
                ("org-a", site1["id"], "usr-sup", "2026-11-06T12:00:00Z"),
            )
            tx.execute(
                "INSERT INTO site_memberships"
                " (organization_id, site_id, user_id, granted_at, revoked_at)"
                " VALUES (?, ?, ?, ?, NULL)",
                ("org-a", site1["id"], "usr-tech", "2026-11-06T12:00:00Z"),
            )
            tx.execute(
                "INSERT INTO site_memberships"
                " (organization_id, site_id, user_id, granted_at, revoked_at)"
                " VALUES (?, ?, ?, ?, NULL)",
                ("org-a", site2["id"], "usr-tech", "2026-11-06T12:00:00Z"),
            )
        asset = create_asset(
            conn, sup, site_id=site1["id"], tag="pump-001", name="Pump 001",
            criticality="medium", purchase_cost_cents=10000, clock=_at(12),
        )
        wo = create_work_order(
            conn, sup, site_id=site1["id"], asset_id=asset["id"], number="wo-100",
            title="Rebuild pump", description="Full rebuild", priority="high",
            requester_id="usr-sup", clock=_at(13),
        )
        return {"sup": sup, "wo": wo, "part": None, "loc": None}

    def test_steps_1_to_4_setup_assignment_denial_and_stock_refusal(self):
        conn = self._open_migrated()
        seeded = self._seed_steps_1_to_4(conn)
        sup = seeded["sup"]
        wo = seeded["wo"]
        self.assertEqual(("site-1", "site-2"), tuple(
            row["code"] for row in conn.execute(
                "SELECT code FROM sites WHERE organization_id = ? ORDER BY created_at, id",
                ("org-a",),
            )
        ))
        self.assertEqual(("open", 1, "high"), (
            wo["status"], wo["version"], wo["priority"],
        ))
        with self.assertRaises(PermissionDeniedError) as caught:
            assign_technician(
                conn, sup, work_order_id=wo["id"], technician_id="usr-orgb",
                assigned_by_id="usr-sup", clock=_at(14),
            )
        self.assertEqual(
            "assignee must be an active technician with access to the site",
            str(caught.exception),
        )
        assign_technician(
                conn, sup, work_order_id=wo["id"], technician_id="usr-tech",
                assigned_by_id="usr-sup", clock=_at(15),
        )
        assigned = conn.execute(
            "SELECT status, version FROM work_orders WHERE id = ?", (wo["id"],)
        ).fetchone()
        self.assertEqual(("assigned", 2), (assigned["status"], assigned["version"]))
        transition_work_order(
            conn, sup, work_order_id=wo["id"], to_status="in_progress",
            expected_version=2, reason=None, actor_id="usr-sup", clock=_at(16),
        )
        part = create_part(
            conn, sup, sku="bolt-m8", name="M8 bolt", unit_of_measure="unit",
            standard_cost_cents=2500, clock=_at(17),
        )
        loc = create_stock_location(conn, sup, code="main", name="Main", clock=_at(18))
        adjust_stock(
            conn, sup, part_id=part["id"], location_id=loc["id"], quantity_delta=1,
            reason="opening", expected_version=1, actor_id="usr-sup", clock=_at(19),
        )
        balance = conn.execute(
            "SELECT on_hand, reserved, version FROM stock_balances"
            " WHERE organization_id = ? AND part_id = ? AND stock_location_id = ?",
            ("org-a", part["id"], loc["id"]),
        ).fetchone()
        self.assertEqual((1, 0, 2), (balance["on_hand"], balance["reserved"], balance["version"]))
        with self.assertRaises(ConflictError) as caught:
            reserve_stock(
                conn, sup, part_id=part["id"], location_id=loc["id"],
                work_order_id=wo["id"], quantity=2, expected_version=2,
                actor_id="usr-sup", clock=_at(20),
            )
        self.assertEqual("reservation exceeds available stock", str(caught.exception))
        balance = conn.execute(
            "SELECT on_hand, reserved, version FROM stock_balances"
            " WHERE organization_id = ? AND part_id = ? AND stock_location_id = ?",
            ("org-a", part["id"], loc["id"]),
        ).fetchone()
        self.assertEqual((1, 0, 2), (balance["on_hand"], balance["reserved"], balance["version"]))


if __name__ == "__main__":
    unittest.main()
