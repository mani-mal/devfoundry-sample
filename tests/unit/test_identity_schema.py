"""Tests for the identity schema migration (T004)."""

import pathlib
import re
import sqlite3
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from opsledger.core.db import connect, transaction  # noqa: E402
from opsledger.core.migrations import migrate  # noqa: E402

RFC3339_Z_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

VALID_ROLES = ("developer", "lead", "auditor", "approver", "purchasing")

_INSERT_ORG_SQL = (
    "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)"
)
_INSERT_USER_SQL = (
    "INSERT INTO users (id, email, display_name, created_at) VALUES (?, ?, ?, ?)"
)
_INSERT_MEMBERSHIP_SQL = (
    "INSERT INTO memberships (organization_id, user_id, role, created_at)"
    " VALUES (?, ?, ?, ?)"
)


def normalize_identity(value: str) -> str:
    return value.lower().strip()


class IdentitySchemaTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = pathlib.Path(self._tmp.name)
        self.db_path = self.tmp_path / "db.sqlite"
        self.conn = connect(str(self.db_path))
        self.addCleanup(self.conn.close)

    def write_migration_copy(self, name):
        """Copy the shipped migrations into a fresh directory named ``name``."""
        migrations_dir = self.tmp_path / name
        migrations_dir.mkdir()
        for source in sorted((ROOT / "opsledger" / "migrations").glob("*.sql")):
            (migrations_dir / source.name).write_bytes(source.read_bytes())
        return migrations_dir

    def make_migrated_database(self):
        migrations_dir = self.write_migration_copy(f"migrated-{id(self)}")
        migrate(self.conn, migrations_dir)
        return migrations_dir


class FreshDatabaseMigrationTests(IdentitySchemaTestBase):
    def test_fresh_database_migrates_0001_then_0002(self):
        migrations_dir = self.write_migration_copy("migrations")

        result = migrate(self.conn, migrations_dir)

        self.assertEqual(result, ["0001_initial", "0002_identity", "0003_sessions", "0004_csrf_contexts", "0005_user_hash_columns", "0006_site_memberships"])
        table_names = {
            row[0]
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        for table in ("schema_migrations", "organizations", "users", "memberships"):
            self.assertIn(table, table_names)
        rows = self.conn.execute(
            "SELECT migration_id, applied_at FROM schema_migrations"
            " ORDER BY migration_id"
        ).fetchall()
        self.assertEqual(len(rows), 6)
        for row in rows:
            self.assertTrue(RFC3339_Z_PATTERN.match(row["applied_at"]))

    def test_running_migrate_again_is_a_no_op(self):
        migrations_dir = self.make_migrated_database()
        before = [
            tuple(row)
            for row in self.conn.execute(
                "SELECT migration_id, checksum, applied_at FROM schema_migrations"
            ).fetchall()
        ]

        result = migrate(self.conn, migrations_dir)

        self.assertEqual(result, [])
        after = [
            tuple(row)
            for row in self.conn.execute(
                "SELECT migration_id, checksum, applied_at FROM schema_migrations"
            ).fetchall()
        ]
        self.assertEqual(before, after)


class OrganizationSlugNormalizationTests(IdentitySchemaTestBase):
    def setUp(self):
        super().setUp()
        self.make_migrated_database()

    def insert_organization(self, organization_id, slug, name="Acme"):
        stored_slug = normalize_identity(slug)
        with transaction(self.conn) as tx:
            tx.execute(
                _INSERT_ORG_SQL,
                (organization_id, stored_slug, name, "2026-11-06T12:00:00Z"),
            )
        return stored_slug

    def stored_organizations(self):
        return self.conn.execute(
            "SELECT id, slug, name, created_at FROM organizations"
        ).fetchall()

    def test_unique_slug_inserts_and_stored_value_is_normalized(self):
        self.insert_organization("org-1", "ACME")

        organizations = self.stored_organizations()
        self.assertEqual(len(organizations), 1)
        self.assertEqual(organizations[0]["id"], "org-1")
        self.assertEqual(organizations[0]["slug"], "acme")
        self.assertEqual(
            organizations[0]["slug"], normalize_identity(organizations[0]["slug"])
        )

    def test_same_slug_again_raises_integrity_error(self):
        self.insert_organization("org-1", "acme")

        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_organization("org-2", "acme")

    def test_different_case_slug_normalized_to_collision_is_rejected(self):
        self.insert_organization("org-1", "acme")

        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_organization("org-2", "  AcMe  ")

        organizations = self.stored_organizations()
        self.assertEqual(len(organizations), 1)
        self.assertEqual(organizations[0]["slug"], "acme")

    def test_non_normalized_slug_is_rejected_by_the_schema(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with transaction(self.conn) as tx:
                tx.execute(
                    _INSERT_ORG_SQL,
                    ("org-x", "  Not Normalized  ", "x", "2026-11-06T12:00:00Z"),
                )

        organizations = self.stored_organizations()
        self.assertEqual(len(organizations), 0)


class UserEmailTestClass(IdentitySchemaTestBase):
    def setUp(self):
        super().setUp()
        self.make_migrated_database()

    def insert_user(self, user_id, email, display_name="Dev"):
        stored_email = normalize_identity(email)
        with transaction(self.conn) as tx:
            tx.execute(
                _INSERT_USER_SQL,
                (user_id, stored_email, display_name, "2026-11-06T12:00:00Z"),
            )
        return stored_email

    def stored_users(self):
        return self.conn.execute(
            "SELECT id, email, display_name, created_at FROM users"
        ).fetchall()

    def test_unique_email_inserts_and_stored_value_is_normalized(self):
        self.insert_user("user-1", "Dev@Example.COM")

        users = self.stored_users()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["id"], "user-1")
        self.assertEqual(users[0]["email"], "dev@example.com")
        self.assertEqual(
            users[0]["email"], normalize_identity(users[0]["email"])
        )

    def test_same_email_again_raises_integrity_error(self):
        self.insert_user("user-1", "dev@example.com")

        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_user("user-2", "dev@example.com")

    def test_different_case_email_normalized_to_collision_is_rejected(self):
        self.insert_user("user-1", "dev@example.com")

        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_user("user-2", "  Dev@Example.com  ")

        users = self.stored_users()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["email"], "dev@example.com")

    def test_non_normalized_email_is_rejected_by_the_schema(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with transaction(self.conn) as tx:
                tx.execute(
                    _INSERT_USER_SQL,
                    ("user-x", " Not@Normalized ", "x", "2026-11-06T12:00:00Z"),
                )

        self.assertEqual(len(self.stored_users()), 0)


class MembershipTestBase(IdentitySchemaTestBase):
    def setUp(self):
        super().setUp()
        self.make_migrated_database()
        self.insert_organization("org-1", "acme")
        self.insert_organization("org-2", "globex")
        self.insert_user("user-1", "dev@example.com")

    def insert_organization(self, organization_id, slug, name="Acme"):
        with transaction(self.conn) as tx:
            tx.execute(
                _INSERT_ORG_SQL,
                (
                    organization_id,
                    normalize_identity(slug),
                    name,
                    "2026-11-06T12:00:00Z",
                ),
            )

    def insert_user(self, user_id, email, display_name="Dev"):
        with transaction(self.conn) as tx:
            tx.execute(
                _INSERT_USER_SQL,
                (user_id, normalize_identity(email), display_name, "2026-11-06T12:00:00Z"),
            )

    def insert_membership(self, organization_id, user_id, role, created_at=None):
        with transaction(self.conn) as tx:
            tx.execute(
                _INSERT_MEMBERSHIP_SQL,
                (
                    organization_id,
                    user_id,
                    role,
                    created_at or "2026-11-06T12:00:00Z",
                ),
            )

    def stored_memberships(self):
        return self.conn.execute(
            "SELECT organization_id, user_id, role, created_at FROM memberships"
        ).fetchall()


class MembershipInsertTests(MembershipTestBase):
    def test_membership_inserts(self):
        self.insert_membership("org-1", "user-1", "developer")

        memberships = self.stored_memberships()
        self.assertEqual(len(memberships), 1)
        self.assertEqual(memberships[0]["organization_id"], "org-1")
        self.assertEqual(memberships[0]["user_id"], "user-1")
        self.assertEqual(memberships[0]["role"], "developer")

    def test_same_user_twice_in_one_organization_raises_integrity_error(self):
        self.insert_membership("org-1", "user-1", "developer")

        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_membership("org-1", "user-1", "lead")

    def test_same_user_in_different_organization_is_fine(self):
        self.insert_membership("org-1", "user-1", "developer")

        self.insert_membership("org-2", "user-1", "auditor")

        memberships = self.stored_memberships()
        self.assertEqual(len(memberships), 2)
        self.assertEqual(
            {(m["organization_id"], m["role"]) for m in memberships},
            {("org-1", "developer"), ("org-2", "auditor")},
        )


class RoleCheckConstraintTests(MembershipTestBase):
    def test_unknown_role_rejected_by_check_constraint(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_membership("org-1", "user-1", "admin")

    def test_each_valid_role_accepted(self):
        for index, role in enumerate(VALID_ROLES):
            organization_id = f"org-{index + 100}"
            user_id = f"user-{index + 100}"
            self.insert_organization(organization_id, f"slug-{index}")
            self.insert_user(user_id, f"dev-{index}@example.com")
            self.insert_membership(organization_id, user_id, role)

        memberships = self.stored_memberships()
        self.assertEqual([m["role"] for m in memberships], list(VALID_ROLES))


class ForeignKeyEnforcementTests(MembershipTestBase):
    def test_membership_missing_organization_fails_foreign_key(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_membership("missing-org", "user-1", "developer")

    def test_membership_missing_user_fails_foreign_key(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_membership("org-1", "missing-user", "developer")


class TimestampFormatTests(MembershipTestBase):
    def test_created_at_values_are_rfc3339_utc_z_second_precision(self):
        self.insert_membership(
            "org-1", "user-1", "developer", created_at="2026-11-06T12:00:02Z"
        )

        memberships = self.stored_memberships()
        self.assertEqual(len(memberships), 1)
        self.assertTrue(RFC3339_Z_PATTERN.match(memberships[0]["created_at"]))
        self.assertTrue(RFC3339_Z_PATTERN.match("2026-11-06T12:00:00Z"))


class MigrationFixtureIntegrityTests(IdentitySchemaTestBase):
    def test_shipped_migrations_apply_to_fresh_database_and_stay_untouched(self):
        migrations_dir = self.write_migration_copy("migrations")
        original = {
            source.name: source.read_bytes()
            for source in sorted((ROOT / "opsledger" / "migrations").glob("*.sql"))
        }

        first = migrate(self.conn, migrations_dir)
        second = migrate(self.conn, migrations_dir)

        self.assertIn("0001_initial", first)
        self.assertIn("0002_identity", first)
        self.assertEqual(second, [])
        for name, content in original.items():
            self.assertEqual(
                (ROOT / "opsledger" / "migrations" / name).read_bytes(), content
            )


if __name__ == "__main__":
    unittest.main()
