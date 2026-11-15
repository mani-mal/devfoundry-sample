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
