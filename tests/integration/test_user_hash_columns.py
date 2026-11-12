"""Integration tests (T011 part C): password-hash columns on the real migrated schema.

These tests apply the REAL shipped migrations to a temporary file database and
then provision users against that migrated schema — no CREATE TABLE anywhere in
the test, unlike the T009 unit tests which build their own users table.
"""

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone

from opsledger.core.clock import FixedClock
from opsledger.core.db import connect
from opsledger.core.errors import ValidationError
from opsledger.core.migrations import migrate
from opsledger.identity import (
    provision_user,
    provision_user_sql,
    verify_password,
)


class UserHashColumnsTests(unittest.TestCase):
    """Integration tests against the real shipped migrations."""

    def _open_migrated(self) -> sqlite3.Connection:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda: connect(tmp.name).close())
        conn = connect(tmp.name)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def test_t1_users_table_has_all_ten_columns(self):
        conn = self._open_migrated()
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        expected = {
            "id",
            "email",
            "display_name",
            "created_at",
            "salt",
            "hash",
            "n",
            "r",
            "p",
            "protocol_version",
        }
        self.assertEqual(expected, columns)

    def test_t2_provision_user_succeeds_against_real_migrated_schema(self):
        conn = self._open_migrated()
        clock = FixedClock(datetime(2026, 11, 6, 12, 0, 0, tzinfo=timezone.utc))
        record = provision_user(
            conn,
            user_id="u-hash-1",
            email="A@Example.com",
            display_name="Hash User",
            password="correct horse battery staple",
            clock=clock,
        )
        self.assertEqual(record.user_id, "u-hash-1")
        stored = (
            conn.execute("SELECT email FROM users WHERE id = ?", ("u-hash-1",))
            .fetchone()[0]
        )
        self.assertEqual("a@example.com", stored)
        self.assertTrue(
            verify_password("correct horse battery staple", record)
        )
        self.assertFalse(verify_password("wrong password", record))

    def test_t3_provision_user_sql_documented_and_duplicate_email_rejected(self):
        conn = self._open_migrated()
        clock = FixedClock(datetime(2026, 11, 6, 12, 0, 0, tzinfo=timezone.utc))
        self.assertIn("users", provision_user_sql)
        self.assertIn("salt", provision_user_sql)
        self.assertIn("hash", provision_user_sql)
        provision_user(
            conn,
            user_id="u-hash-2",
            email="dup@Example.com",
            display_name="Dup One",
            password="first password",
            clock=clock,
        )
        with self.assertRaises(ValidationError) as ctx:
            provision_user(
                conn,
                user_id="u-hash-3",
                email="dup@example.com",
                display_name="Dup Two",
                password="second password",
                clock=clock,
            )
        self.assertNotIsInstance(ctx.exception, sqlite3.Error)
