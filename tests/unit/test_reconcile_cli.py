"""Unit tests (T040, M5): the reconciliation CLI.

Exercises the argparse subcommand through ``main`` with redirect (no
subprocess): matching balances exit 0 printing one JSON object; unknown
part/location surface the public message on stderr with exit 1 and no
traceback; a disagreeing balance (tampered movement) exits 1. The CLI is
a thin adapter: it resolves the part's organization and calls
:func:`opsledger.inventory.reconcile_balance` -- no business rules here.
"""

import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect
from opsledger.core.migrations import migrate
from opsledger.inventory import adjust_stock
from opsledger.parts import create_part, create_stock_location
from opsledger.reconcile_cli import main as reconcile_main


class ReconcileCliTest(unittest.TestCase):
    def _open_migrated(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda p=tmp.name: os.path.exists(p) and os.unlink(p))
        self._db_path = tmp.name
        self.addCleanup(lambda: connect(tmp.name).close())
        conn = connect(tmp.name)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def _tick_clock(self):
        self._tick = getattr(self, "_tick", 0) + 1
        return FixedClock(datetime(2026, 11, 13, 12, self._tick, 0, tzinfo=timezone.utc))

    def _seed(self, conn, on_hand=5):
        with conn:
            conn.execute(
                "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                ("org-cli", "org-cli", "Organization CLI", "2026-11-06T12:00:00Z"),
            )
        context = OrganizationContext(organization_id="org-cli", actor_id="user-111")
        part = create_part(
            conn, context, sku="bolt-m8", name="M8 bolt", unit_of_measure="unit",
            standard_cost_cents=2500, clock=self._tick_clock(),
        )
        location = create_stock_location(conn, context, code="main", name="Main store", clock=self._tick_clock())
        adjust_stock(
            conn, context, part_id=part["id"], location_id=location["id"],
            quantity_delta=on_hand, reason="opening", expected_version=1,
            actor_id=context.actor_id, clock=self._tick_clock(),
        )
        return part, location

    def _run_cli(self, argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = reconcile_main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_t1_matching_balances_exit_0_printing_one_json_object(self):
        conn = self._open_migrated()
        part, location = self._seed(conn)
        code, out, err = self._run_cli([
            self._db_path, "--part", part["id"], "--location", location["id"],
        ])
        self.assertEqual(0, code)
        self.assertEqual("", err)
        payload = json.loads(out)
        self.assertTrue(payload["matches"])
        self.assertEqual((5, 0), (payload["on_hand_sum"], payload["reserved_sum"]))
        self.assertEqual(part["id"], payload["balance"]["part_id"])

    def test_t2_unknown_part_and_location_exit_1_with_public_message(self):
        conn = self._open_migrated()
        part, location = self._seed(conn)
        code, out, err = self._run_cli([
            self._db_path, "--part", "prt-unknown", "--location", location["id"],
        ])
        self.assertEqual(1, code)
        self.assertEqual("part not found", err.strip())
        self.assertEqual("", out)
        code, out, err = self._run_cli([
            self._db_path, "--part", part["id"], "--location", "stl-unknown",
        ])
        self.assertEqual(1, code)
        self.assertEqual("stock location not found", err.strip())
        self.assertEqual("", out)

    def test_t3_disagreeing_balance_exits_1_naming_the_drift(self):
        conn = self._open_migrated()
        part, location = self._seed(conn, on_hand=5)
        with conn:
            conn.execute(
                "INSERT INTO stock_movements (id, organization_id, part_id, stock_location_id,"
                " operation, on_hand_delta, reserved_delta, reason, work_order_id, actor_id, created_at)"
                " VALUES ('stm-tamper', 'org-cli', ?, ?, 'adjust', 3, 0, 'tamper', NULL, 'user-111',"
                " '2026-11-13T12:00:00Z')",
                (part["id"], location["id"]),
            )
        code, out, err = self._run_cli([
            self._db_path, "--part", part["id"], "--location", location["id"],
        ])
        self.assertEqual(1, code)
        payload = json.loads(out)
        self.assertFalse(payload["matches"])
        self.assertEqual(8, payload["on_hand_sum"])
        self.assertEqual(5, payload["balance"]["on_hand"])

    def test_t4_cli_module_documents_the_adapter_pattern(self):
        import pathlib

        source = pathlib.Path("opsledger/reconcile_cli.py").read_text(encoding="utf-8")
        self.assertIn("reconcile_balance", source)
        self.assertIn("raise SystemExit(main())", source)


if __name__ == "__main__":
    unittest.main()
