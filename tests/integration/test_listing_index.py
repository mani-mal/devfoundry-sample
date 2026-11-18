"""Integration tests (T068, M9): assets listing index.

Applies the REAL shipped migrations to temporary file databases and
exercises the asset listing through public service functions plus plain
SQL inspection only. Acceptance (spec M9/T068): migration 24 ships the
covering index; plans use it instead of a TEMP B-TREE sort; results are
identical with and without the index; keyset paging covers tied rows
exactly once.
"""

import os
import tempfile
import unittest

from opsledger.core import OrganizationContext
from opsledger.core.db import connect
from opsledger.core.migrations import migrate
from opsledger.assets.listing import list_assets

_SEED_ORGS_TEXT = "2026-11-06T12:00:00Z"
_SEED_ASSET_TEXT = "2026-11-18T12:02:00Z"
_FIXED_SITE_ID = "site-fixed0000000000000000000000000000"
_LISTING_SQL = (
    "SELECT id, organization_id, site_id, tag, name, criticality,"
    " purchase_cost_cents, version, created_at, updated_at, archived_at"
    " FROM assets WHERE organization_id = ? AND archived_at IS NULL"
    " ORDER BY created_at ASC, id ASC LIMIT ?"
)


class ListingIndexTests(unittest.TestCase):
    def _open_migrated(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda p=tmp.name: os.path.exists(p) and os.unlink(p))
        self.addCleanup(lambda: connect(tmp.name).close())
        conn = connect(tmp.name)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def _seed_assets(self, conn, ids):
        with conn:
            conn.execute(
                "INSERT INTO organizations (id, slug, name, created_at)"
                " VALUES (?, ?, ?, ?)",
                ("org-aaa", "org-aaa", "Organization AAA", _SEED_ORGS_TEXT),
            )
            conn.execute(
                "INSERT INTO organizations (id, slug, name, created_at)"
                " VALUES (?, ?, ?, ?)",
                ("org-bbb", "org-bbb", "Organization BBB", _SEED_ORGS_TEXT),
            )
            conn.execute(
                "INSERT INTO sites (id, organization_id, code, name,"
                " timezone, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    _FIXED_SITE_ID,
                    "org-aaa",
                    "main",
                    "Main store",
                    "UTC",
                    _SEED_ORGS_TEXT,
                ),
            )
            for asset_id in ids:
                conn.execute(
                    "INSERT INTO assets (id, organization_id, site_id, tag,"
                    " name, criticality, purchase_cost_cents, version,"
                    " created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        asset_id,
                        "org-aaa",
                        _FIXED_SITE_ID,
                        asset_id,
                        "Asset " + asset_id,
                        "low",
                        1000,
                        1,
                        _SEED_ASSET_TEXT,
                        _SEED_ASSET_TEXT,
                    ),
                )

    def test_migrations_include_the_listing_index(self):
        conn = self._open_migrated()
        with conn:
            migration_count = conn.execute(
                "SELECT COUNT(*) FROM schema_migrations"
            ).fetchone()[0]
            index_count = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='index'"
                " AND name='idx_assets_org_created'"
            ).fetchone()[0]
        self.assertEqual(24, migration_count)
        self.assertEqual(1, index_count)

    def test_listing_results_are_identical_with_and_without_the_index(self):
        first = self._open_migrated()
        second = self._open_migrated()
        ids = [f"asset-{i:0>12}" for i in range(12)]
        self._seed_assets(first, ids)
        self._seed_assets(second, ids)
        with first:
            first.execute("DROP INDEX idx_assets_org_created")
        plan = first.execute(
            "EXPLAIN QUERY PLAN " + _LISTING_SQL, ("org-aaa", 200)
        ).fetchall()
        self.assertTrue(
            any("TEMP B-TREE FOR ORDER BY" in row[3] for row in plan), plan
        )
        plan = second.execute(
            "EXPLAIN QUERY PLAN " + _LISTING_SQL, ("org-aaa", 200)
        ).fetchall()
        self.assertTrue(
            any("idx_assets_org_created" in row[3] for row in plan), plan
        )
        context = OrganizationContext(organization_id="org-aaa", actor_id="user-111")
        without_index = [tuple(r) for r in list_assets(first, context, limit=200)]
        with_index = [tuple(r) for r in list_assets(second, context, limit=200)]
        self.assertEqual(with_index, without_index)

    def test_page_walk_covers_every_row_exactly_once_with_ties(self):
        conn = self._open_migrated()
        ids = [f"asset-{i:0>12}" for i in range(12)]
        self._seed_assets(conn, ids)
        context = OrganizationContext(organization_id="org-aaa", actor_id="user-111")
        expected = [tuple(r) for r in list_assets(conn, context, limit=200)]
        walked = []
        cursor = None
        while True:
            page = list_assets(
                conn,
                context,
                limit=5,
                after_created_at=None if cursor is None else cursor["after_created_at"],
                after_id=None if cursor is None else cursor["after_id"],
            )
            if not page:
                break
            walked.extend(tuple(r) for r in page)
            last = page[-1]
            cursor = {"after_created_at": last["created_at"], "after_id": last["id"]}
        self.assertEqual(expected, walked)

    def test_plan_uses_the_covering_index_not_temp_btree(self):
        conn = self._open_migrated()
        ids = [f"asset-{i:0>12}" for i in range(12)]
        self._seed_assets(conn, ids)
        plan = conn.execute(
            "EXPLAIN QUERY PLAN " + _LISTING_SQL, ("org-aaa", 200)
        ).fetchall()
        self.assertFalse(
            any("TEMP B-TREE FOR ORDER BY" in row[3] for row in plan), plan
        )
        self.assertTrue(
            any("idx_assets_org_created" in row[3] for row in plan), plan
        )


if __name__ == "__main__":
    unittest.main()
