"""Integration tests (T065): backup/restore round trip over temporary file databases.

Applies the REAL shipped migrations to temporary file databases and
exercises the backup/restore module through its public functions only.
Acceptance: a backup copies committed state; a restored database keeps
schema, rows, and referential invariants; refused inputs store nothing.
"""

import sqlite3
import os
import tempfile
import unittest
from datetime import datetime, timezone

from opsledger.core import OrganizationContext
from opsledger.core.backup import (
    BACKUP_BUSY_SOURCE_MESSAGE,
    BACKUP_MISSING_MESSAGE,
    BACKUP_SOURCE_TYPE_MESSAGE,
    backup_database,
    restore_database,
)
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect
from opsledger.core.errors import ValidationError
from opsledger.core.migrations import migrate
from opsledger.parts import create_part, create_stock_location


class BackupRestoreTest(unittest.TestCase):
    def _open_migrated(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda: connect(tmp.name).close())
        conn = connect(tmp.name)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def _context(self):
        return OrganizationContext(organization_id="org-aaa", actor_id="user-111")

    def _seed_business_rows(self, conn):
        with conn:
            conn.execute(
                "INSERT INTO organizations (id, slug, name, created_at) VALUES ('org-aaa', 'org-aaa', 'Organization AAA', '2026-11-06T12:00:00Z')"
            )
        create_part(
            conn, self._context(), sku="bolt-m8", name="M8 bolt",
            unit_of_measure="unit", standard_cost_cents=2500,
            clock=FixedClock(datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc)),
        )
        create_stock_location(
            conn, self._context(), code="main", name="Main store",
            clock=FixedClock(datetime(2026, 11, 18, 12, 1, 0, tzinfo=timezone.utc)),
        )

    def _tmp_path(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda: sqlite3.connect(tmp.name).close())
        return tmp.name

    def test_backup_copies_committed_state_and_restores_invariants(self):
        src = self._open_migrated()
        self._seed_business_rows(src)
        backup_path = self._tmp_path()
        backup_database(src, backup_path)
        restore_path = self._tmp_path()
        restored = restore_database(backup_path, restore_path)
        self.addCleanup(restored.close)
        self.assertEqual(24, restored.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0])
        row = restored.execute("SELECT slug FROM organizations WHERE id = 'org-aaa'").fetchone()
        self.assertEqual("org-aaa", row[0])
        self.assertEqual(1, restored.execute("SELECT COUNT(*) FROM parts").fetchone()[0])
        self.assertEqual("ok", restored.execute("PRAGMA integrity_check").fetchone()[0])
        self.assertEqual([], restored.execute("PRAGMA foreign_key_check").fetchall())

    def test_backup_refuses_busy_source(self):
        conn = self._open_migrated()
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO organizations (id, slug, name, created_at) VALUES ('org-aaa', 'org-aaa', 'Organization AAA', '2026-11-06T12:00:00Z')"
        )
        self.addCleanup(conn.close)
        with self.assertRaises(ValidationError) as caught:
            backup_database(conn, self._tmp_path())
        self.assertEqual(BACKUP_BUSY_SOURCE_MESSAGE, str(caught.exception))

    def test_backup_refuses_non_connection_source(self):
        with self.assertRaises(ValidationError) as caught:
            backup_database("not-a-connection", self._tmp_path())
        self.assertEqual(BACKUP_SOURCE_TYPE_MESSAGE, str(caught.exception))

    def test_restore_refuses_missing_backup_file(self):
        missing_path = self._tmp_path()
        os.unlink(missing_path)
        with self.assertRaises(ValidationError) as caught:
            restore_database(missing_path, self._tmp_path())
        self.assertEqual(BACKUP_MISSING_MESSAGE, str(caught.exception))

    def test_restored_connection_uses_opsledger_profile(self):
        src = self._open_migrated()
        self._seed_business_rows(src)
        backup_path = self._tmp_path()
        backup_database(src, backup_path)
        restored = restore_database(backup_path, self._tmp_path())
        self.addCleanup(restored.close)
        self.assertEqual("wal", restored.execute("PRAGMA journal_mode").fetchone()[0])
        self.assertEqual(1, restored.execute("PRAGMA foreign_keys").fetchone()[0])
        self.assertIsInstance(restored, sqlite3.Connection)


if __name__ == "__main__":
    unittest.main()
