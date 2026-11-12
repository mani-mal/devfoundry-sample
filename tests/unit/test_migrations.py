"""Tests for the migration runner and history checksums (T003)."""

import hashlib
import pathlib
import re
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from opsledger.core.db import connect  # noqa: E402
from opsledger.core.errors import ConflictError, ValidationError  # noqa: E402
from opsledger.core.migrations import migrate  # noqa: E402

RFC3339_Z_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class FixedClock:
    def __init__(self, instant: datetime) -> None:
        self._instant = instant.astimezone(timezone.utc).replace(microsecond=0)

    def now(self):
        return self._instant

    def timestamp(self):
        return self._instant.strftime("%Y-%m-%dT%H:%M:%SZ")


class MigrationTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = pathlib.Path(self._tmp.name)
        self.db_path = self.tmp_path / "db.sqlite"
        self.conn = connect(str(self.db_path))
        self.addCleanup(self.conn.close)

    def make_directory(self):
        directory = self.tmp_path / "migrations"
        directory.mkdir()
        return directory

    def write_sql(self, directory, name, content):
        (directory / name).write_text(content, encoding="utf-8")

    def history_rows(self):
        return self.conn.execute(
            "SELECT migration_id, checksum, applied_at FROM schema_migrations"
        ).fetchall()

    def history_ids(self):
        return [row["migration_id"] for row in self.history_rows()]

    def table_names(self):
        return {
            row[0]
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    def sqlite_master_sql(self):
        return " ".join(
            row[0] or ""
            for row in self.conn.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        )


class EmptyDirectoryTests(MigrationTestBase):
    def test_empty_directory_migrates_nothing_and_creates_history_table(self):
        directory = self.make_directory()

        result = migrate(self.conn, directory)

        self.assertEqual(result, [])
        self.assertIn("schema_migrations", self.table_names())
        self.assertNotIn("schema_notes", self.table_names())
        self.assertEqual(len(self.history_rows()), 0)


class AppliedMigrationTests(MigrationTestBase):
    def test_migration_applies_and_records_checksum_and_utc_applied_at(self):
        directory = self.make_directory()
        self.write_sql(
            directory,
            "0001_create_items.sql",
            "CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT NOT NULL)",
        )
        expected_digest = hashlib.sha256(
            (directory / "0001_create_items.sql").read_bytes()
        ).hexdigest()

        result = migrate(self.conn, directory)

        self.assertEqual(result, ["0001_create_items"])
        rows = self.history_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["migration_id"], "0001_create_items")
        self.assertEqual(rows[0]["checksum"], expected_digest)
        self.assertTrue(RFC3339_Z_PATTERN.match(rows[0]["applied_at"]))
        self.assertIn("items", self.table_names())

    def test_applied_at_is_deterministic_with_injected_clock(self):
        directory = self.make_directory()
        self.write_sql(
            directory,
            "0001_create_items.sql",
            "CREATE TABLE items (id INTEGER PRIMARY KEY)",
        )
        clock = FixedClock(datetime(2026, 11, 6, 12, 0, 0, tzinfo=timezone.utc))

        migrate(self.conn, directory, clock=clock)

        rows = self.history_rows()
        self.assertEqual(rows[0]["applied_at"], "2026-11-06T12:00:00Z")
        self.assertTrue(RFC3339_Z_PATTERN.match(rows[0]["applied_at"]))


class SecondRunNoOpTests(MigrationTestBase):
    def test_second_run_is_a_no_op(self):
        directory = self.make_directory()
        self.write_sql(
            directory,
            "0001_create_items.sql",
            "CREATE TABLE items (id INTEGER PRIMARY KEY)",
        )
        migrate(self.conn, directory)
        first = [tuple(row) for row in self.history_rows()]

        result = migrate(self.conn, directory)

        self.assertEqual(result, [])
        second = [tuple(row) for row in self.history_rows()]
        self.assertEqual(len(first), len(second))
        self.assertEqual(first, second)


class TamperEvidenceTests(MigrationTestBase):
    def test_editing_applied_file_raises_conflict_error_and_applies_nothing(self):
        directory = self.make_directory()
        self.write_sql(
            directory,
            "0001_create_items.sql",
            "CREATE TABLE items (id INTEGER PRIMARY KEY)",
        )
        migrate(self.conn, directory)
        self.write_sql(
            directory,
            "0001_create_items.sql",
            "CREATE TABLE items (id INTEGER PRIMARY KEY, extra TEXT)",
        )
        self.write_sql(
            directory,
            "0002_add_index.sql",
            "CREATE TABLE later (id INTEGER PRIMARY KEY)",
        )
        before = before_tables = self.table_names()

        with self.assertRaises(ConflictError) as caught:
            migrate(self.conn, directory)

        self.assertEqual(caught.exception.code, "conflict")
        self.assertIn("0001_create_items", str(caught.exception))
        self.assertNotIn("later", self.table_names())
        self.assertEqual(before_tables, self.table_names())
        self.assertEqual(len(self.history_rows()), 1)

    def test_multiple_mismatches_named_and_nothing_applied(self):
        directory = self.make_directory()
        self.write_sql(
            directory,
            "0001_create_items.sql",
            "CREATE TABLE items (id INTEGER PRIMARY KEY)",
        )
        self.write_sql(
            directory,
            "0002_second.sql",
            "CREATE TABLE second (id INTEGER PRIMARY KEY)",
        )
        migrate(self.conn, directory)
        self.write_sql(
            directory,
            "0001_create_items.sql",
            "CREATE TABLE items (id INTEGER PRIMARY KEY, extra TEXT)",
        )
        self.write_sql(
            directory,
            "0002_second.sql",
            "CREATE TABLE second (id INTEGER PRIMARY KEY, extra TEXT)",
        )
        before = self.sqlite_master_sql()

        with self.assertRaises(ConflictError) as caught:
            migrate(self.conn, directory)

        self.assertIn("0001_create_items", str(caught.exception))
        self.assertIn("0002_second", str(caught.exception))
        self.assertEqual(before, self.sqlite_master_sql())


class FilenameValidationTests(MigrationTestBase):
    def test_file_without_numeric_prefix_raises_validation_error(self):
        directory = self.make_directory()
        self.write_sql(directory, "initial.sql", "CREATE TABLE one (id INTEGER)")

        with self.assertRaises(ValidationError) as caught:
            migrate(self.conn, directory)

        self.assertNotIn("one", self.table_names())
        self.assertEqual(len(self.history_rows()), 0)


class RollbackOnStatementFailureTests(MigrationTestBase):
    def test_statement_failure_rolls_back_statements_and_history_row(self):
        directory = self.make_directory()
        self.write_sql(
            directory,
            "0001_create_items.sql",
            "CREATE TABLE items (id INTEGER PRIMARY KEY)",
        )
        migrate(self.conn, directory)
        self.write_sql(
            directory,
            "0002_bad.sql",
            "CREATE TABLE ok_table (id INTEGER PRIMARY KEY);\n"
            "INSERT INTO missing_table VALUES (1);",
        )

        with self.assertRaises(sqlite3.OperationalError):
            migrate(self.conn, directory)

        self.assertNotIn("ok_table", self.table_names())
        self.assertEqual(len(self.history_rows()), 1)
        self.assertEqual(self.history_ids(), ["0001_create_items"])


class GapToleranceTests(MigrationTestBase):
    def test_missing_number_is_not_an_error_and_applies_when_it_reappears(self):
        directory = self.make_directory()
        self.write_sql(
            directory,
            "0001_create_items.sql",
            "CREATE TABLE items (id INTEGER PRIMARY KEY)",
        )
        migrate(self.conn, directory)

        second_directory = self.tmp_path / "migrations_with_gap"
        second_directory.mkdir()
        self.write_sql(
            second_directory,
            "0001_create_items.sql",
            "CREATE TABLE items (id INTEGER PRIMARY KEY)",
        )

        migrate(self.conn, second_directory)

        self.write_sql(
            second_directory,
            "0002_gap_reappears.sql",
            "CREATE TABLE later (id INTEGER PRIMARY KEY)",
        )
        result = migrate(self.conn, second_directory)
        self.assertEqual(result, ["0002_gap_reappears"])
        self.assertEqual(len(self.history_rows()), 2)


class StatementOrderingTests(MigrationTestBase):
    def test_migrations_apply_in_numeric_prefix_order(self):
        directory = self.make_directory()
        self.write_sql(
            directory,
            "0002_second.sql",
            "CREATE TABLE second (id INTEGER PRIMARY KEY)",
        )
        self.write_sql(
            directory,
            "0001_first.sql",
            "CREATE TABLE first (id INTEGER PRIMARY KEY)",
        )

        result = migrate(self.conn, directory)

        self.assertEqual(result, ["0001_first", "0002_second"])
        self.assertEqual(self.history_ids(), ["0001_first", "0002_second"])


class RepositoryFixtureTest(unittest.TestCase):
    def test_repository_migration_fixture_applies_to_fresh_database(self):
        _tmp = tempfile.TemporaryDirectory()
        self.addCleanup(_tmp.cleanup)
        root = pathlib.Path(__file__).resolve().parents[2]
        migrations_dir = root / "opsledger" / "migrations"
        db_path = pathlib.Path(_tmp.name) / "fresh.sqlite"
        fresh_conn = connect(str(db_path))
        self.addCleanup(fresh_conn.close)

        first = migrate(fresh_conn, migrations_dir)
        second = migrate(fresh_conn, migrations_dir)

        self.assertIn("0001_initial", first)
        self.assertEqual(second, [])
        self.assertEqual(
            fresh_conn.execute("SELECT COUNT(*) FROM schema_notes").fetchone()[0],
            0,
        )


if __name__ == "__main__":
    unittest.main()
