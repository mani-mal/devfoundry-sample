"""Tests for bounded contention handling in opsledger.core.contention (T067)."""

import pathlib
import sqlite3
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from opsledger.core.contention import (  # noqa: E402
    DB_LOCKED_CONFLICT_MESSAGE,
    run_locked,
)
from opsledger.core.db import connect  # noqa: E402
from opsledger.core.errors import ConflictError  # noqa: E402


class ContentionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = str(pathlib.Path(self._tmp.name) / "db.sqlite")
        self.conn = connect(self.path)
        self.addCleanup(self.conn.close)

    def _conn(self):
        conn = connect(self.path)
        self.addCleanup(conn.close)
        return conn

    def test_run_locked_commits_on_success(self):
        conn = self._conn()
        conn.execute("CREATE TABLE t (value INTEGER)")
        conn.commit()

        rowcount = run_locked(
            conn, lambda c: c.execute("INSERT INTO t VALUES (7)").rowcount
        )

        self.assertEqual(rowcount, 1)
        second = self._conn()
        visible = second.execute("SELECT COUNT(*) FROM t").fetchone()[0]
        self.assertEqual(visible, 1)

    def test_run_locked_rolls_back_and_reraises_fn_errors(self):
        conn = self._conn()
        conn.execute("CREATE TABLE t (value INTEGER)")
        conn.commit()

        def fn(c):
            c.execute("INSERT INTO t VALUES (42)")
            raise ValueError("boom")

        with self.assertRaises(ValueError) as caught:
            run_locked(conn, fn)

        self.assertEqual(str(caught.exception), "boom")
        self.assertNotIsInstance(caught.exception, ConflictError)
        second = self._conn()
        visible = second.execute("SELECT COUNT(*) FROM t").fetchone()[0]
        self.assertEqual(visible, 0)

    def test_run_locked_maps_lock_exhaustion_to_conflict_error(self):
        real = self._conn()

        class AlwaysLockedConn:
            def __init__(self, inner):
                self._inner = inner

            def execute(self, sql, *args):
                raise sqlite3.OperationalError("database is locked")

            def commit(self):
                self._inner.commit()

            def rollback(self):
                self._inner.rollback()

        delays = []

        def stub_sleeper(delay):
            delays.append(delay)

        calls = []

        def fn(conn):
            calls.append(conn)

        with self.assertRaises(ConflictError) as caught:
            run_locked(
                AlwaysLockedConn(real), fn, max_attempts=3, sleeper=stub_sleeper
            )

        self.assertEqual(str(caught.exception), DB_LOCKED_CONFLICT_MESSAGE)
        self.assertEqual(self._delays_seen(delays), [0.05, 0.1])
        self.assertEqual(len(calls), 0)

    def test_run_locked_succeeds_after_one_busy_round(self):
        real = self._conn()
        real.execute("CREATE TABLE t (value INTEGER)")
        real.commit()

        class BusyOnceConn:
            def __init__(self, inner):
                self._inner = inner
                self.begin_calls = 0

            def execute(self, sql, *args):
                if sql.strip().upper() == "BEGIN IMMEDIATE":
                    self.begin_calls += 1
                    if self.begin_calls == 1:
                        raise sqlite3.OperationalError("database is locked")
                return self._inner.execute(sql, *args)

            def commit(self):
                self._inner.commit()

            def rollback(self):
                self._inner.rollback()

        delays = []

        def stub_sleeper(delay):
            delays.append(delay)

        stub_conn = BusyOnceConn(real)

        result = run_locked(
            stub_conn,
            lambda c: c.execute("INSERT INTO t VALUES (5)").rowcount,
            max_attempts=3,
            sleeper=stub_sleeper,
        )

        self.assertEqual(result, 1)
        self.assertEqual(stub_conn.begin_calls, 2)
        self.assertEqual(self._delays_seen(delays), [0.05])

    def test_run_locked_single_attempt_no_retries(self):
        real = self._conn()

        class AlwaysLockedConn:
            def __init__(self, inner):
                self._inner = inner

            def execute(self, sql, *args):
                raise sqlite3.OperationalError("database is locked")

            def commit(self):
                self._inner.commit()

            def rollback(self):
                self._inner.rollback()

        delays = []

        def stub_sleeper(delay):
            delays.append(delay)

        with self.assertRaises(ConflictError):
            run_locked(
                AlwaysLockedConn(real),
                lambda c: None,
                max_attempts=1,
                sleeper=stub_sleeper,
            )

        self.assertEqual(len(delays), 0)

    @staticmethod
    def _delays_seen(delays):
        return list(delays)


if __name__ == "__main__":
    unittest.main()
