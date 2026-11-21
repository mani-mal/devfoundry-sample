"""T077 (A10) checklist-gate regression: completion vs open mandatory items.

On main (af59203) both completed paths transitioned with an open mandatory
checklist item: the module fix (task BEFORE this one) adds the gate so
transition_work_order and transition_work_order_with_reservations raise
ConflictError with the exact message "work order has incomplete mandatory
checklist items" BEFORE any transaction opens, leaving status and version
unchanged; completing the item lets the same transition succeed.
"""

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from opsledger.assets import create_asset, create_site
from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect, transaction
from opsledger.core.errors import ConflictError
from opsledger.core.migrations import migrate
from opsledger.workorders import (
    add_checklist_item, assign_technician, checklist_completion_blocked,
    complete_checklist_item, create_work_order,
)
from opsledger.workorders.reservation_rules import transition_work_order_with_reservations
from opsledger.workorders.transitions import transition_work_order

MESSAGE = "work order has incomplete mandatory checklist items"


def _at(seconds: int) -> FixedClock:
    return FixedClock(
        datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    )

class ChecklistGateRegressionTests(unittest.TestCase):
    def _open_migrated(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda p=tmp.name: os.path.exists(p) and os.unlink(p))
        self.addCleanup(lambda: connect(tmp.name).close())
        conn = connect(tmp.name)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def _seed(self, conn):
        with transaction(conn) as tx:
            tx.execute(
                "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                ("org-a", "org-a", "Org A", "2026-11-06T12:00:00Z"),
            )
            tx.execute(
                "INSERT INTO users (id, email, display_name, created_at) VALUES (?, ?, ?, ?)",
                ("u1", "u1@example.com", "User One", "2026-11-06T12:00:00Z"),
            )
        context = OrganizationContext(organization_id="org-a", actor_id="u1")
        site = create_site(conn, context, code="s1", name="S", clock=_at(1))
        with transaction(conn) as tx:
            tx.execute(
                "INSERT INTO site_memberships"
                " (organization_id, site_id, user_id, granted_at, revoked_at)"
                " VALUES (?, ?, ?, ?, NULL)",
                ("org-a", site["id"], "u1", "2026-11-06T12:00:00Z"),
            )
        asset = create_asset(
            conn, context, site_id=site["id"], tag="p-1", name="P",
            criticality="low", purchase_cost_cents=100, clock=_at(2),
        )
        work_order = create_work_order(
            conn, context, site_id=site["id"], asset_id=asset["id"],
            number="wo-1", title="T", description="D", priority="high",
            requester_id="u1", clock=_at(3),
        )
        assign_technician(
            conn, context, work_order_id=work_order["id"],
            technician_id="u1", assigned_by_id="u1", clock=_at(4),
        )
        in_progress = transition_work_order(
            conn, context, work_order_id=work_order["id"], to_status="in_progress",
            expected_version=2, reason=None, actor_id="u1", clock=_at(5),
        )
        return context, in_progress

    def test_completion_blocked_with_open_mandatory_item_on_both_paths(self):
        for transition in (transition_work_order, transition_work_order_with_reservations):
            with self.subTest(transition=transition.__name__):
                conn = self._open_migrated()
                context, in_progress = self._seed(conn)
                item = add_checklist_item(
                    conn, context, work_order_id=in_progress["id"],
                    label="mandatory step", mandatory=True, clock=_at(6),
                )
                blocked = checklist_completion_blocked(conn, context, work_order_id=in_progress["id"])
                self.assertEqual(["mandatory step"], blocked)
                snapshot = conn.execute(
                    "SELECT status, version FROM work_orders WHERE id = ?", (in_progress["id"],)
                ).fetchone()
                with self.assertRaises(ConflictError) as caught:
                    transition(
                        conn, context, work_order_id=in_progress["id"],
                        to_status="completed", expected_version=in_progress["version"],
                        reason=None, actor_id="u1", clock=_at(7),
                    )
                self.assertEqual(MESSAGE, str(caught.exception))
                after = conn.execute(
                    "SELECT status, version FROM work_orders WHERE id = ?", (in_progress["id"],)
                ).fetchone()
                self.assertEqual(dict(snapshot), dict(after))
                complete_checklist_item(conn, context, item_id=item["id"], clock=_at(8))
                completed = transition(
                    conn, context, work_order_id=in_progress["id"],
                    to_status="completed", expected_version=in_progress["version"],
                    reason=None, actor_id="u1", clock=_at(9),
                )
                self.assertEqual("completed", completed["status"])

    def test_optional_item_never_blocks_completion(self):
        conn = self._open_migrated()
        context, in_progress = self._seed(conn)
        add_checklist_item(
            conn, context, work_order_id=in_progress["id"],
            label="photo", mandatory=False, clock=_at(6),
        )
        self.assertEqual([], checklist_completion_blocked(conn, context, work_order_id=in_progress["id"]))
        completed = transition_work_order(
            conn, context, work_order_id=in_progress["id"], to_status="completed",
            expected_version=in_progress["version"], reason=None, actor_id="u1", clock=_at(7),
        )
        self.assertEqual("completed", completed["status"])


if __name__ == "__main__":
    unittest.main()
