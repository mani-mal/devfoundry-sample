"""T073 injection regression tests (APP14: traversal, symlink, SQL
injection, script text; part 1 of 2).

Two methods here: hostile paths fail with one identical canonical error
shape, and hostile text (script tags, CSV/SQL injection strings) is stored
and returned as DATA only — never executed and never able to touch the
schema. Part 2 (CSV, sort-injection and import tests) is added to this
file by a follow-up task.
"""

import csv
import io
import os
import sys
import tempfile
import unittest
import pathlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from opsledger.assets import create_asset, create_site
from opsledger.assets.listing import list_assets
from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect, transaction
from opsledger.core.errors import (
    ConflictError,
    PermissionDeniedError,
    ValidationError,
)
from opsledger.core.migrations import migrate
from opsledger.http.envelope import InputError
from opsledger.http.static import resolve_static
from opsledger.reporting.csv_export import CSV_HEADER, export_work_orders
from opsledger.reporting.search import search
from opsledger.workorders import create_work_order

ORG_ID = "org-inj"


class _Actor:
    """Minimal authorization stub: role attribute only."""

    def __init__(self, role):
        self.role = role


class InjectionRegressionTests(unittest.TestCase):
    """Regression coverage for T073 injection handling (part 1)."""

    def setUp(self):
        self._clock_step = 0

    def _open_migrated(self):
        """Open a temporary file database with the REAL shipped migrations."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda p=tmp.name: os.path.exists(p) and os.unlink(p))
        self.addCleanup(lambda: connect(tmp.name).close())
        conn = connect(tmp.name)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def _tick_clock(self):
        """Each call one second later from 2026-11-18T12:00:00Z."""
        self._clock_step += 1
        return FixedClock(
            datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc)
            + timedelta(seconds=self._clock_step)
        )

    def _seed_org_fixture(self, conn, organization_id):
        with transaction(conn) as tx:
            tx.execute(
                "INSERT OR IGNORE INTO organizations (id, slug, name, created_at)"
                " VALUES (?, ?, ?, ?)",
                (
                    organization_id,
                    organization_id,
                    "Organization " + organization_id,
                    "2026-11-06T12:00:00Z",
                ),
            )
        create_site(conn, OrganizationContext(organization_id=organization_id),
                    code="hq", name="Headquarters", clock=self._tick_clock())

    def test_traversal_and_hostile_paths_fail_identically(self):
        web_root = Path(ROOT) / "web"
        for evil in (
            "/../secrets.db",
            "/../../etc/passwd",
            "/a/../../etc/passwd",
            "/x\x00y",
            "/a\\b",
            "/....//config",
            "/%2e%2e/secrets.db",
            "/web/../opledger/cli.py",
        ):
            with self.assertRaises(InputError) as caught:
                resolve_static(web_root, evil)
            error = caught.exception
            self.assertEqual(error.status, 404)
            self.assertEqual(error.code, "not_found")
            self.assertEqual(error.message, "static file not found")
            self.assertNotIn(str(evil), error.message)
        with tempfile.TemporaryDirectory() as outside:
            with tempfile.TemporaryDirectory() as copy_root:
                index = Path(copy_root) / "index.html"
                index.write_bytes((web_root / "index.html").read_bytes())
                link = Path(copy_root) / "danger.link"
                os.symlink("/etc/passwd", link)
                with self.assertRaises(InputError) as caught:
                    resolve_static(copy_root, "/danger.link")
                self.assertEqual(caught.exception.status, 404)
                self.assertEqual(caught.exception.code, "not_found")
                self.assertEqual(caught.exception.message, "static file not found")

    def test_script_text_is_data_never_executed(self):
        conn = self._open_migrated()
        self._seed_org_fixture(conn, ORG_ID)
        context = OrganizationContext(organization_id=ORG_ID)
        site = conn.execute("SELECT * FROM sites LIMIT 1").fetchone()
        seed_asset = create_asset(
            conn, context, site_id=site["id"], tag="seed-1",
            name="Seed asset", criticality="low", purchase_cost_cents=0,
            clock=self._tick_clock(),
        )
        created = create_work_order(
            conn, context, site_id=site["id"], asset_id=seed_asset["id"],
            number="wo-1", title="<script>alert(1)</script>",
            description="x'); DROP TABLE work_orders;--", priority="high",
            requester_id="user-1", clock=self._tick_clock(),
        )
        self.assertEqual(created["title"], "<script>alert(1)</script>")
        self.assertEqual(created["description"], "x'); DROP TABLE work_orders;--")
        tables_before = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
        ).fetchone()[0]
        create_work_order(
            conn, context, site_id=site["id"], asset_id=seed_asset["id"],
            number="wo-2", title="x'); DROP TABLE work_orders;--",
            description="<script>alert(1)</script>", priority="high",
            requester_id="user-1", clock=self._tick_clock(),
        )
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0], 2)
        tables_after = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
        ).fetchone()[0]
        self.assertEqual(tables_after, tables_before)
        create_asset(
            conn, context, site_id=site["id"], tag="evil-1",
            name="1'); DROP TABLE assets;--", criticality="low",
            purchase_cost_cents=0, clock=self._tick_clock(),
        )
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0], 2)
        matches = search(
            conn, context, actor=_Actor("admin"),
            query="'; DROP TABLE assets;--")
        for kind in ("assets", "work_orders", "parts"):
            self.assertEqual(len(matches[kind]), 0)
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0], 2)

    def test_csv_export_formula_injection_and_hostile_cells(self):
        conn = self._open_migrated()
        self._seed_org_fixture(conn, ORG_ID)
        context = OrganizationContext(organization_id=ORG_ID)
        site = conn.execute("SELECT * FROM sites LIMIT 1").fetchone()
        asset = create_asset(
            conn, context, site_id=site["id"], tag="wo-asset",
            name="Work order asset", criticality="low",
            purchase_cost_cents=0, clock=self._tick_clock(),
        )
        titles = ("=SUM(A1)", "+CMD", "-2+2", "@xp_cmdshell", "a,b\nc")
        for index, title in enumerate(titles, start=1):
            created = create_work_order(
                conn, context, site_id=site["id"], asset_id=asset["id"],
                number="wo-" + str(index), title=title,
                description="x", priority="low",
                requester_id="user-1", clock=self._tick_clock(),
            )
            self.assertEqual(created["title"], title)
        text = export_work_orders(conn, context, actor=_Actor("auditor"))
        rows = list(csv.reader(io.StringIO(text)))
        self.assertEqual(rows[0], CSV_HEADER)
        self.assertEqual(
            [cell for cell in rows[0] if cell.startswith(("=", "+", "-", "@"))],
            [],
        )
        rendered = [row[2] for row in rows[1:]]
        self.assertEqual(len(rows), 6)
        self.assertEqual(
            [cell for cell in rendered if cell.startswith("'")],
            ["'=SUM(A1)", "'+CMD", "'-2+2", "'@xp_cmdshell"],
        )
        quoted_rows = [row for row in rows[1:] if row[1] == "wo-5"]
        self.assertEqual(len(quoted_rows), 1)
        self.assertEqual(quoted_rows[0][2], "a,b\nc")
        self.assertNotIn("=SUM(A1)", rendered)
        self.assertNotIn("+CMD", rendered)
        self.assertNotIn("-2+2", rendered)
        self.assertNotIn("@xp_cmdshell", rendered)
        with self.assertRaises(PermissionDeniedError):
            export_work_orders(conn, context, actor=_Actor("admin"))

    def test_sort_and_limit_injection_rejected(self):
        conn = self._open_migrated()
        self._seed_org_fixture(conn, ORG_ID)
        context = OrganizationContext(organization_id=ORG_ID)
        site = conn.execute("SELECT * FROM sites LIMIT 1").fetchone()
        first = create_asset(
            conn, context, site_id=site["id"], tag="tag-1",
            name="pump-1", criticality="low", purchase_cost_cents=1,
            clock=self._tick_clock(),
        )
        second = create_asset(
            conn, context, site_id=site["id"], tag="tag-2",
            name="valve-2", criticality="low", purchase_cost_cents=2,
            clock=self._tick_clock(),
        )
        self.assertNotEqual(first["id"], second["id"])
        for limit in (-1, 0, 201, 10**9, True, "50", 50.0):
            with self.assertRaises(ValidationError):
                list_assets(conn, context, limit=limit)
        with self.assertRaises(ValidationError):
            list_assets(conn, context,
                        after_created_at="2026-11-18T00:00:00Z")
        with self.assertRaises(ValidationError):
            list_assets(conn, context, after_id="a-1")
        rows = list_assets(
            conn, context,
            after_created_at="x' OR 1=1 --", after_id="a'")
        self.assertEqual(len(rows), 0)
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0], 2)
        ordered = list_assets(conn, context, limit=2)
        keys = [(row["created_at"], row["id"]) for row in ordered]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(len(keys), 2)
        wildcard = search(
            conn, context, actor=_Actor("admin"), query="pump%")
        self.assertEqual(len(wildcard["assets"]), 0)
        plain = search(
            conn, context, actor=_Actor("admin"), query="pump")
        self.assertGreaterEqual(len(plain["assets"]), 1)
        self.assertEqual(ConflictError("x").code, "conflict")


if __name__ == "__main__":
    unittest.main()
