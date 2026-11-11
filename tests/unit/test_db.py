"""Tests for the SQLite connection factory and transaction context (T002)."""

import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from opsledger.core.db import connect  # noqa: E402
from opsledger.core.errors import ConflictError  # noqa: E402


class ConnectPragmaTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = str(pathlib.Path(self._tmp.name) / "db.sqlite")

    def test_foreign_keys_pragma_is_on_after_connect(self):
        conn = self.addCleanupCaller(conn := connect(self.path))
        row = conn.execute("PRAGMA foreign_keys").fetchone()
        self.assertEqual(row[0], 1)

    def addCleanupCaller(self, conn):
        self.addCleanup(conn.close)
        return conn

    def test_journal_mode_is_wal(self):
        conn = self.addCleanupCaller(connect(self.path))
        row = conn.execute("PRAGMA journal_mode").fetchone()
        self.assertEqual(str(row[0]), "wal")

    def test_synchronous_pragma_is_normal(self):
        conn = self.addCleanupCaller(connect(self.path))
        row = conn.execute("PRAGMA synchronous").fetchone()
        self.assertEqual(row[0], 1)

    def test_row_factory_is_sqlite3_row(self):
        conn = self.addCleanupCaller(connect(self.path))
        self.assertIs(conn.row_factory, __import__("sqlite3").Row)


class TransactionCommitTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = str(pathlib.Path(self._tmp.name) / "db.sqlite")
        self.conn = connect(self.path)
        self.addCleanup(self.conn.close)
        self.conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")

    def test_clean_block_commits_and_row_persists(self):
        from opsledger.core.db import transaction

        with transaction(self.conn) as tx:
            tx.execute("INSERT INTO items (name) VALUES (?)", ("wrench",))

        row = self.conn.execute(
            "SELECT name FROM items WHERE id = ?", (1,)
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["name"], "wrench")

    def test_connection_returns_tx_object(self):
        from opsledger.core.db import transaction

        with transaction(self.conn) as tx:
            self.assertIs(type(tx).__name__, type(self.conn).__name__)


class TransactionRollbackTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = str(pathlib.Path(self._tmp.name) / "db.sqlite")
        self.conn = connect(self.path)
        self.addCleanup(self.conn.close)
        self.conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")

    def test_exception_inside_block_rolls_back_row_absent(self):
        from opsledger.core.db import transaction

        class Boom(Exception):
            pass

        with self.assertRaises(Boom):
            with transaction(self.conn) as tx:
                tx.execute("INSERT INTO items (name) VALUES (?)", ("lost",))
                raise Boom()

        count = self.conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        self.assertEqual(count, 0)

    def test_original_exception_propagates_not_wrapped(self):
        from opsledger.core.db import transaction

        class Boom(Exception):
            pass

        try:
            with transaction(self.conn):
                raise Boom("original")
        except Boom as caught:
            self.assertEqual(str(caught), "original")
        else:
            self.fail("Boom was not re-raised")


class NestedTransactionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = str(pathlib.Path(self._tmp.name) / "db.db")
        self.conn = connect(self.path)
        self.addCleanup(self.conn.close)

    def test_nested_transaction_raises_conflict_error(self):
        from opsledger.core.db import transaction

        with transaction(self.conn):
            with self.assertRaises(ConflictError) as caught:
                with transaction(self.conn):
                    pass
        self.assertEqual(caught.exception.code, "conflict")

    def test_nested_message_is_public_no_traceback(self):
        from opsledger.core.db import transaction

        with transaction(self.conn):
            with self.assertRaises(ConflictError) as caught:
                with transaction(self.conn):
                    pass
        message = str(caught.exception)
        self.assertNotIn("Traceback", message)
        self.assertNotIn("File ", message)
        self.assertTrue(len(message) > 0)

    def test_outer_exits_cleanly_after_nested_rejection(self):
        from opsledger.core.db import transaction

        with transaction(self.conn) as tx:
            with self.assertRaises(ConflictError):
                with transaction(tx):
                    pass
            tx.execute("CREATE TABLE after (id INTEGER PRIMARY KEY)")
            tx.execute("INSERT INTO after VALUES (1)")

        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM after").fetchone()[0], 1
        )


class DatabaseErrorPropagationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = str(pathlib.Path(self._tmp.name) / "db.sqlite")
        self.conn = connect(self.path)
        self.addCleanup(self.conn.close)
        self.conn.execute(
            "CREATE TABLE parts (id INTEGER PRIMARY KEY, code TEXT UNIQUE)"
        )

    def test_integrity_error_propagates_unchanged(self):
        import sqlite3

        from opsledger.core.db import transaction

        with transaction(self.conn) as tx:
            tx.execute("INSERT INTO parts (code) VALUES (?)", ("P-1",))

        with self.assertRaises(sqlite3.IntegrityError):
            with transaction(self.conn) as tx:
                tx.execute("INSERT INTO parts (code) VALUES (?)", ("P-1",))

        self.assertEqual(
            self.conn.execute("SELECT code FROM parts").fetchone()["code"], "P-1"
        )

    def test_operational_error_propagates_unchanged(self):
        import sqlite3

        from opsledger.core.db import transaction

        with self.assertRaises(sqlite3.OperationalError):
            with transaction(self.conn) as tx:
                tx.execute("INSERT INTO nonexistent_table VALUES (1)")


if __name__ == "__main__":
    unittest.main()
