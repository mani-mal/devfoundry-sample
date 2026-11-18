"""T071 upgrade fixture and restore diagnostics tests: builds prior-milestone
databases through the REAL shipped migrations and exercises the upgrade
fixture module through public functions only. Acceptance: prior database
applies migrations only through the milestone boundary; upgrade applies the
remaining migrations; rows, ids, and recorded history survive the upgrade;
non-connection arguments are rejected.
"""

import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from opsledger.core.clock import FixedClock
from opsledger.core.errors import ValidationError
from opsledger.core.upgrade_fixtures import (
    MILESTONE_BOUNDARIES,
    build_prior_database,
    restore_diagnostics,
    upgrade_database,
)

_CLOCK = FixedClock(datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc))


class UpgradeFixtureTests(unittest.TestCase):
    def _tmp_path(self):
        path = Path(tempfile.mkdtemp(prefix="upgrade-fixture-tests-")) / "fixture.db"
        self.addCleanup(lambda d=str(Path(path).parent): shutil.rmtree(d, True))
        return str(path)

    def test_prior_database_applies_only_through_boundary(self):
        conn = build_prior_database(
            self._tmp_path(), boundary=MILESTONE_BOUNDARIES["m5"], clock=_CLOCK
        )
        try:
            self.assertEqual(
                17, conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
            )
            self.assertEqual(
                "0017_stock_ledger",
                conn.execute(
                    "SELECT migration_id FROM schema_migrations"
                    " ORDER BY migration_id DESC LIMIT 1"
                ).fetchone()[0],
            )
            diagnostics = restore_diagnostics(conn)
            self.assertEqual("ok", diagnostics["integrity"])
            self.assertEqual(0, diagnostics["foreign_key_violations"])
            self.assertEqual(17, diagnostics["applied_migration_count"])
        finally:
            conn.close()

    def test_upgrade_applies_the_remaining_migrations(self):
        conn = build_prior_database(
            self._tmp_path(), boundary=MILESTONE_BOUNDARIES["m5"], clock=_CLOCK
        )
        try:
            applied = upgrade_database(conn, clock=_CLOCK)
            self.assertEqual(7, len(applied))
            self.assertEqual("0024_assets_listing_idx", applied[-1])
            diagnostics = restore_diagnostics(conn)
            self.assertEqual(24, diagnostics["applied_migration_count"])
            self.assertEqual("ok", diagnostics["integrity"])
            self.assertEqual(0, diagnostics["foreign_key_violations"])
        finally:
            conn.close()

    def test_upgrade_preserves_rows_ids_and_history(self):
        conn = build_prior_database(
            self._tmp_path(), boundary=MILESTONE_BOUNDARIES["m5"], clock=_CLOCK
        )
        try:
            original_applied_at = conn.execute(
                "SELECT applied_at FROM schema_migrations WHERE migration_id = '0017_stock_ledger'"
            ).fetchone()[0]
            with conn:
                conn.execute(
                    "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                    ("org-upgrade-check", "upgrade-check", "Upgrade Check", "2026-11-18T12:00:00Z"),
                )
            applied = upgrade_database(conn, clock=_CLOCK)
            self.assertEqual(7, len(applied))
            row = conn.execute(
                "SELECT id, slug, name, created_at FROM organizations WHERE id = 'org-upgrade-check'"
            ).fetchone()
            self.assertEqual(
                ("org-upgrade-check", "upgrade-check", "Upgrade Check", "2026-11-18T12:00:00Z"),
                tuple(row),
            )
            self.assertEqual(
                original_applied_at,
                conn.execute(
                    "SELECT applied_at FROM schema_migrations WHERE migration_id = '0017_stock_ledger'"
                ).fetchone()[0],
            )
            self.assertEqual(
                24, conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
            )
        finally:
            conn.close()

    def test_upgrade_database_rejects_non_connection(self):
        with self.assertRaises(ValidationError):
            upgrade_database(object())
        with self.assertRaises(ValidationError):
            restore_diagnostics(object())


if __name__ == "__main__":
    unittest.main()
