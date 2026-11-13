"""Integration tests (T011 part D): the auth service against the real migrations.

These tests apply the REAL shipped migrations to a temporary file database, provision
one user, and exercise the auth service functions (login, logout, resolve_session,
LOGIN_FAILURE_MESSAGE) against that migrated schema. No CREATE TABLE anywhere in the
test file; PermissionDeniedError is imported from opsledger.core.errors.
"""

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone

from opsledger.core.clock import FixedClock
from opsledger.core.db import connect
from opsledger.core.errors import PermissionDeniedError
from opsledger.core.migrations import migrate
from opsledger.identity import provision_user
from opsledger.identity.service import (
    LOGIN_FAILURE_MESSAGE,
    logout,
    resolve_session,
)
from opsledger.identity.service import login

TEST_USER_ID = "usr-a"
TEST_EMAIL = "a@example.com"
TEST_PASSWORD = "correct horse battery staple"


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, 6, hour, minute, 0, tzinfo=timezone.utc)


class AuthServiceTests(unittest.TestCase):
    """Integration tests for the auth service functions against the real migrations."""

    def _open_migrated(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda: connect(tmp.name).close())
        conn = connect(tmp.name)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def _provision_user(self, conn):
        return provision_user(
            conn,
            user_id=TEST_USER_ID,
            email=TEST_EMAIL,
            display_name="A",
            password=TEST_PASSWORD,
            clock=FixedClock(_at(12, 0)),
        )

    def test_t1_login_correct_email_password_returns_resolvable_token(self):
        conn = self._open_migrated()
        self._provision_user(conn)
        raw_token, session_record, user_id = login(
            conn, email=TEST_EMAIL, password=TEST_PASSWORD, clock=FixedClock(_at(12, 1))
        )
        self.assertEqual(TEST_USER_ID, user_id)
        self.assertEqual(TEST_USER_ID, session_record.user_id)
        self.assertTrue(isinstance(raw_token, str) and raw_token)
        resolved = resolve_session(conn, raw_token=raw_token, clock=FixedClock(_at(12, 2)))
        self.assertIsNotNone(resolved)
        self.assertTrue(isinstance(resolved, sqlite3.Row))
        self.assertEqual(TEST_USER_ID, resolved["user_id"])

    def test_t2_login_wrong_password_raises_permission_denied_login_message(self):
        conn = self._open_migrated()
        self._provision_user(conn)
        with self.assertRaises(PermissionDeniedError) as ctx:
            login(
                conn,
                email=TEST_EMAIL,
                password="wrong password",
                clock=FixedClock(_at(12, 1)),
            )
        self.assertEqual(LOGIN_FAILURE_MESSAGE, str(ctx.exception))
        self.assertEqual("permission_denied", ctx.exception.code)

    def test_t3_login_unknown_email_matches_wrong_password_failure_exactly(self):
        conn = self._open_migrated()
        self._provision_user(conn)
        with self.assertRaises(PermissionDeniedError) as unknown_email_ctx:
            login(
                conn,
                email="nobody@example.com",
                password=TEST_PASSWORD,
                clock=FixedClock(_at(12, 1)),
            )
        with self.assertRaises(PermissionDeniedError) as wrong_password_ctx:
            login(
                conn,
                email=TEST_EMAIL,
                password="wrong password",
                clock=FixedClock(_at(12, 1)),
            )
        self.assertEqual(
            str(unknown_email_ctx.exception), str(wrong_password_ctx.exception)
        )
        self.assertEqual(
            unknown_email_ctx.exception.code, wrong_password_ctx.exception.code
        )
        self.assertEqual(LOGIN_FAILURE_MESSAGE, str(unknown_email_ctx.exception))
        self.assertEqual("permission_denied", unknown_email_ctx.exception.code)

    def test_t4_login_email_lookup_is_case_insensitive(self):
        conn = self._open_migrated()
        self._provision_user(conn)
        raw_token, _session_record, user_id = login(
            conn, email="A@Example.COM", password=TEST_PASSWORD, clock=FixedClock(_at(12, 1))
        )
        self.assertEqual(TEST_USER_ID, user_id)
        resolved = resolve_session(conn, raw_token=raw_token, clock=FixedClock(_at(12, 2)))
        self.assertIsNotNone(resolved)
        self.assertEqual(TEST_USER_ID, resolved["user_id"])
        self.assertEqual(TEST_EMAIL, resolved["email"])

    def test_t5_resolve_session_none_for_unknown_revoked_and_expired(self):
        conn = self._open_migrated()
        self._provision_user(conn)
        self.assertIsNone(
            resolve_session(conn, raw_token="unknown-token", clock=FixedClock(_at(12, 1)))
        )
        revoked_token, _record, _user_id = login(
            conn, email=TEST_EMAIL, password=TEST_PASSWORD, clock=FixedClock(_at(12, 2))
        )
        logout(conn, raw_token=revoked_token, clock=FixedClock(_at(12, 3)))
        self.assertIsNone(
            resolve_session(conn, raw_token=revoked_token, clock=FixedClock(_at(12, 4)))
        )
        expired_token, _record2, _user_id2 = login(
            conn, email=TEST_EMAIL, password=TEST_PASSWORD, clock=FixedClock(_at(14, 0))
        )
        conn.execute(
            "UPDATE sessions SET expires_at = ? WHERE user_id = ?",
            ("2026-11-06T13:00:00Z", TEST_USER_ID),
        )
        self.assertIsNone(
            resolve_session(conn, raw_token=expired_token, clock=FixedClock(_at(15, 0)))
        )

    def test_t6_resolve_session_returns_joined_row_for_live_session(self):
        conn = self._open_migrated()
        self._provision_user(conn)
        raw_token, _record, _user_id = login(
            conn, email=TEST_EMAIL, password=TEST_PASSWORD, clock=FixedClock(_at(12, 1))
        )
        resolved = resolve_session(conn, raw_token=raw_token, clock=FixedClock(_at(12, 2)))
        self.assertIsNotNone(resolved)
        self.assertEqual(TEST_USER_ID, resolved["user_id"])
        self.assertEqual(TEST_EMAIL, resolved["email"])
        self.assertEqual("A", resolved["display_name"])

    def test_t7_logout_revokes_and_second_logout_is_silent(self):
        conn = self._open_migrated()
        self._provision_user(conn)
        raw_token, _record, _user_id = login(
            conn, email=TEST_EMAIL, password=TEST_PASSWORD, clock=FixedClock(_at(12, 1))
        )
        logout(conn, raw_token=raw_token, clock=FixedClock(_at(12, 2)))
        self.assertIsNone(
            resolve_session(conn, raw_token=raw_token, clock=FixedClock(_at(12, 3)))
        )
        logout(conn, raw_token=raw_token, clock=FixedClock(_at(12, 4)))

    def test_t8_login_after_logout_creates_new_session(self):
        conn = self._open_migrated()
        self._provision_user(conn)
        old_token, _record, _user_id = login(
            conn, email=TEST_EMAIL, password=TEST_PASSWORD, clock=FixedClock(_at(12, 1))
        )
        logout(conn, raw_token=old_token, clock=FixedClock(_at(12, 2)))
        new_token, _record2, _user_id2 = login(
            conn, email=TEST_EMAIL, password=TEST_PASSWORD, clock=FixedClock(_at(12, 3))
        )
        self.assertNotEqual(old_token, new_token)
        self.assertIsNotNone(
            resolve_session(conn, raw_token=new_token, clock=FixedClock(_at(12, 4)))
        )
        self.assertIsNone(
            resolve_session(conn, raw_token=old_token, clock=FixedClock(_at(12, 4)))
        )
        count = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE user_id = ?", (TEST_USER_ID,)
        ).fetchone()[0]
        self.assertEqual(2, count)
