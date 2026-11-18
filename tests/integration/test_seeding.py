"""Synthetic seeding tests (T069): deterministic scale seeding core.

Applies the REAL shipped migrations to temporary file databases and
exercises the seeding module through public functions only. Acceptance:
spec counts match; same seed is deterministic across batch sizes;
different seed diverges; restart after partial state converges; balances
reconcile with movement replay; medium integrity is clean.
"""

import os
import tempfile
import unittest

from opsledger.core.db import connect
from opsledger.core.migrations import migrate
from opsledger.core.seeding import build_manifest, logical_checksum, seed_profile


class SeedingTests(unittest.TestCase):
    def _open_migrated(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda p=tmp.name: os.path.exists(p) and os.unlink(p))
        self.addCleanup(os.unlink, tmp.name)
        self.addCleanup(lambda: connect(tmp.name).close())
        conn = connect(tmp.name)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def test_tiny_profile_matches_spec_counts(self):
        conn = self._open_migrated()
        seed_profile(conn)
        self.assertEqual(2, conn.execute("SELECT COUNT(*) FROM organizations").fetchone()[0])
        self.assertEqual(4, conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0])
        self.assertEqual(20, conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0])
        self.assertEqual(40, conn.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0])
        self.assertEqual(100, conn.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0])
        self.assertEqual(2, conn.execute("SELECT COUNT(*) FROM stock_balances").fetchone()[0])
        self.assertEqual("ok", conn.execute("PRAGMA integrity_check").fetchone()[0])
        self.assertEqual([], list(conn.execute("PRAGMA foreign_key_check")))

    def test_same_seed_is_deterministic_across_batch_sizes(self):
        conn_a = self._open_migrated()
        seed_profile(conn_a, batch_size=64)
        conn_b = self._open_migrated()
        seed_profile(conn_b, batch_size=17)
        self.assertEqual(logical_checksum(conn_a), logical_checksum(conn_b))
        manifest_a = build_manifest(conn_a, profile="tiny", seed=20261118, batch_size=64)
        manifest_b = build_manifest(conn_b, profile="tiny", seed=20261118, batch_size=17)
        self.assertEqual(
            {key: value for key, value in manifest_a.items() if key != "batch_size"},
            {key: value for key, value in manifest_b.items() if key != "batch_size"},
        )

    def test_different_seed_produces_different_rows(self):
        conn_a = self._open_migrated()
        seed_profile(conn_a, seed=20261118)
        conn_b = self._open_migrated()
        seed_profile(conn_b, seed=999)
        self.assertNotEqual(logical_checksum(conn_a), logical_checksum(conn_b))

    def test_restart_after_partial_state_converges(self):
        conn = self._open_migrated()
        seed_profile(conn)
        original_checksum = logical_checksum(conn)
        with conn:
            conn.execute("DELETE FROM stock_movements")
            conn.execute("DELETE FROM stock_balances")
            conn.execute("DELETE FROM work_orders")
        seed_profile(conn)
        self.assertEqual(original_checksum, logical_checksum(conn))
        self.assertEqual(40, conn.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0])
        self.assertEqual(100, conn.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0])
        self.assertEqual(2, conn.execute("SELECT COUNT(*) FROM stock_balances").fetchone()[0])

    def test_balances_reconcile_with_movement_replay(self):
        conn = self._open_migrated()
        seed_profile(conn)
        rows = list(conn.execute(
            "SELECT b.id, b.on_hand, b.reserved, COALESCE(SUM(m.on_hand_delta), 0),"
            " COALESCE(SUM(m.reserved_delta), 0)"
            " FROM stock_balances b"
            " LEFT JOIN stock_movements m"
            " ON m.organization_id = b.organization_id"
            " AND m.part_id = b.part_id"
            " AND m.stock_location_id = b.stock_location_id"
            " GROUP BY b.id, b.on_hand, b.reserved"
        ))
        self.assertEqual(2, len(rows))
        for balance_id, on_hand, reserved, movement_on_hand, movement_reserved in rows:
            self.assertEqual(on_hand, movement_on_hand, balance_id)
            self.assertEqual(reserved, movement_reserved, balance_id)
            self.assertGreaterEqual(on_hand, 0, balance_id)
            self.assertGreaterEqual(reserved, 0, balance_id)

    def test_medium_profile_counts_and_integrity(self):
        conn = self._open_migrated()
        seed_profile(conn, profile="medium", batch_size=512)
        self.assertEqual(3, conn.execute("SELECT COUNT(*) FROM organizations").fetchone()[0])
        self.assertEqual(15, conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0])
        self.assertEqual(5000, conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0])
        self.assertEqual(25000, conn.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0])
        self.assertEqual(100000, conn.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0])
        self.assertEqual("ok", conn.execute("PRAGMA integrity_check").fetchone()[0])
        self.assertEqual([], list(conn.execute("PRAGMA foreign_key_check")))
