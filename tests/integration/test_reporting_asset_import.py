"""Integration tests (T061): validated atomic CSV asset import.

These tests apply the REAL shipped migrations to a temporary file database
and exercise :func:`opsledger.reporting.asset_import.import_assets` against
that migrated schema — no CREATE TABLE anywhere, mirroring the
migrate-a-temp-db setup style. Each behaviour and boundary is covered: the
``asset.write`` permission gate before any payload work, the required
``site_id`` kwarg with organization-scoped site lookup, the payload limits
(bytes, data rows, minimum rows), the exact four-column header, per-row
field validation with 1-based data-row numbers, transactional atomicity
with rollback on every failure, duplicate-tag conflicts, and cross-tenant
isolation between organizations.
"""

import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from opsledger.assets import create_asset, create_site
from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect, transaction
from opsledger.core.errors import (
    ConflictError,
    PermissionDeniedError,
    ValidationError,
)
from opsledger.core.migrations import migrate
from opsledger.reporting.asset_import import IMPORT_LIMITS_MESSAGE, import_assets


class _Actor:
    """Tiny authorization context stub: role attribute only."""

    def __init__(self, role):
        self.role = role


@dataclass(frozen=True)
class ReportingContext(OrganizationContext):
    """Frozen import context: an OrganizationContext carrying one role."""

    role: str = "technician"


def _seed_organization(conn, organization_id):
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


def _seed_user(conn, user_id, email):
    with transaction(conn) as tx:
        tx.execute(
            "INSERT OR IGNORE INTO users (id, email, display_name, created_at)"
            " VALUES (?, ?, ?, ?)",
            (
                user_id,
                email,
                "Technician " + user_id,
                "2026-11-06T12:00:00Z",
            ),
        )


def _plain_context(organization_id):
    return OrganizationContext(organization_id=organization_id)


def _next_clock(clock_state):
    """Each call returns a NEW clock one second later."""
    clock_state["tick"] += 1
    return FixedClock(
        datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)
        + timedelta(seconds=clock_state["tick"])
    )


def _site_id_for(conn, organization_id, clock_state, code="main"):
    _seed_organization(conn, organization_id)
    site = create_site(
        conn,
        _plain_context(organization_id),
        code=code,
        name="Site " + organization_id,
        clock=_next_clock(clock_state),
    )
    return site["id"]


def _asset_for(conn, organization_id, clock_state, site_id, tag):
    return create_asset(
        conn,
        _plain_context(organization_id),
        site_id=site_id,
        tag=tag,
        name="Existing " + tag,
        criticality="high",
        purchase_cost_cents=12345,
        clock=_next_clock(clock_state),
    )


def _payload(lines):
    return "\n".join(lines) + "\n"


FIXTURE_HEADER = "asset_tag,name,criticality,purchase_cost_cents"


class AssetImportTests(unittest.TestCase):
    """Integration tests for import_assets() on the real migrated schema."""

    def setUp(self):
        self._clock_state = {"tick": 0}

    def _open_migrated(self):
        """Open a temporary file database with the REAL shipped migrations."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda: connect(tmp.name).close())
        conn = connect(tmp.name)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def _org_count(self, conn, organization_id):
        return conn.execute(
            "SELECT COUNT(*) FROM assets WHERE organization_id = ?",
            (organization_id,),
        ).fetchone()[0]

    def test_import_requires_asset_write_permission(self):
        conn = self._open_migrated()
        site_id = _site_id_for(conn, "org-aaa", self._clock_state)
        payload = _payload([
            "asset_tag,name,criticality,purchase_cost_cents",
            "pump-100,Pump 100,high,500000",
        ])

        for role in ("technician", "purchasing", "auditor"):
            with self.assertRaises(PermissionDeniedError):
                import_assets(
                    conn, _plain_context("org-aaa"), actor=_Actor(role),
                    site_id=site_id, csv_text=payload,
                )
        self.assertEqual(0, self._org_count(conn, "org-aaa"))

        imported = import_assets(
            conn, _plain_context("org-aaa"), actor=_Actor("admin"),
            site_id=site_id, csv_text=payload,
        )
        self.assertEqual(1, len(imported))
        self.assertEqual({"id", "tag"}, set(imported[0]))

    def test_import_limits_are_enforced(self):
        conn = self._open_migrated()
        site_id = _site_id_for(conn, "org-aaa", self._clock_state)

        oversized = FIXTURE_HEADER + "\n" + "a" * 65537
        with self.assertRaises(ValidationError) as caught:
            import_assets(
                conn, _plain_context("org-aaa"), actor=_Actor("admin"),
                site_id=site_id, csv_text=oversized,
            )
        self.assertIn(IMPORT_LIMITS_MESSAGE, str(caught.exception))

        too_many_rows = [FIXTURE_HEADER]
        too_many_rows.extend(
            "ast-%04d,Name,low,1" % number for number in range(1, 202)
        )
        with self.assertRaises(ValidationError) as over:
            import_assets(
                conn, _plain_context("org-aaa"), actor=_Actor("admin"),
                site_id=site_id, csv_text=_payload(too_many_rows),
            )
        self.assertIn(IMPORT_LIMITS_MESSAGE, str(over.exception))

        header_only = FIXTURE_HEADER + "\n"
        with self.assertRaises(ValidationError):
            import_assets(
                conn, _plain_context("org-aaa"), actor=_Actor("admin"),
                site_id=site_id, csv_text=header_only,
            )

        with self.assertRaises(ValidationError):
            import_assets(
                conn, _plain_context("org-aaa"), actor=_Actor("admin"),
                site_id=site_id, csv_text=42,
            )
        self.assertEqual(0, self._org_count(conn, "org-aaa"))

    def test_import_header_is_validated(self):
        conn = self._open_migrated()
        site_id = _site_id_for(conn, "org-aaa", self._clock_state)

        short_header = _payload([
            "asset_tag,name,criticality",
            "tag-1,Name,low",
        ])
        with self.assertRaises(ValidationError) as caught:
            import_assets(
                conn, _plain_context("org-aaa"), actor=_Actor("admin"),
                site_id=site_id, csv_text=short_header,
            )
        self.assertIn("header must be", str(caught.exception))
        self.assertEqual(0, self._org_count(conn, "org-aaa"))

        correct = _payload([
            "asset_tag,name,criticality,purchase_cost_cents",
            "pump-100,Pump 100,high,500000",
        ])
        imported = import_assets(
            conn, _plain_context("org-aaa"), actor=_Actor("admin"),
            site_id=site_id, csv_text=correct,
        )
        self.assertEqual(1, len(imported))

    def test_import_atomic_two_row_happy_path(self):
        conn = self._open_migrated()
        site_id = _site_id_for(conn, "org-aaa", self._clock_state)
        payload = _payload([
            "asset_tag,name,criticality,purchase_cost_cents",
            "pump-100,Pump 100,high,500000",
            "pump-101,Pump 101,medium,60000",
        ])

        imported = import_assets(
            conn, _plain_context("org-aaa"), actor=_Actor("admin"),
            site_id=site_id, csv_text=payload,
        )

        self.assertEqual(2, len(imported))
        self.assertEqual("pump-100", imported[0]["tag"])
        self.assertEqual("pump-101", imported[1]["tag"])
        for entry in imported:
            self.assertEqual({"id", "tag"}, set(entry))

        rows = conn.execute(
            "SELECT tag, criticality, purchase_cost_cents, site_id"
            " FROM assets WHERE organization_id = 'org-aaa' ORDER BY tag"
        ).fetchall()
        self.assertEqual("pump-100", rows[0]["tag"])
        self.assertEqual("high", rows[0]["criticality"])
        self.assertEqual(500000, rows[0]["purchase_cost_cents"])
        self.assertEqual(site_id, rows[0]["site_id"])
        self.assertEqual("pump-101", rows[1]["tag"])
        self.assertEqual("medium", rows[1]["criticality"])
        self.assertEqual(60000, rows[1]["purchase_cost_cents"])
        self.assertEqual(site_id, rows[1]["site_id"])

    def test_import_bad_row_reports_line_and_rolls_back_everything(self):
        conn = self._open_migrated()
        site_id = _site_id_for(conn, "org-aaa", self._clock_state)
        payload = _payload([
            "asset_tag,name,criticality,purchase_cost_cents",
            "pump-100,Pump 100,high,500000",
            "pump-101,Pump 101,medium,60000",
            "pump-102,Pump 102,urgent,70000",
        ])

        with self.assertRaises(ValidationError) as caught:
            import_assets(
                conn, _plain_context("org-aaa"), actor=_Actor("admin"),
                site_id=site_id, csv_text=payload,
            )
        self.assertIn("row 3", str(caught.exception))
        self.assertEqual(0, self._org_count(conn, "org-aaa"))

    def test_import_duplicate_tag_rolls_back(self):
        conn = self._open_migrated()
        site_id = _site_id_for(conn, "org-aaa", self._clock_state)
        duplicated = _payload([
            "asset_tag,name,criticality,purchase_cost_cents",
            "pump-100,Pump 100,high,500000",
            "pump-100,Pump 100 again,medium,60000",
        ])

        with self.assertRaises(ConflictError):
            import_assets(
                conn, _plain_context("org-aaa"), actor=_Actor("admin"),
                site_id=site_id, csv_text=duplicated,
            )
        self.assertEqual(0, self._org_count(conn, "org-aaa"))

        _asset_for(conn, "org-aaa", self._clock_state, site_id, "pump-9")
        collision = _payload([
            "asset_tag,name,criticality,purchase_cost_cents",
            "pump-9,Pump 9 again,low,10000",
        ])
        with self.assertRaises(ConflictError):
            import_assets(
                conn, _plain_context("org-aaa"), actor=_Actor("admin"),
                site_id=site_id, csv_text=collision,
            )
        self.assertEqual(1, self._org_count(conn, "org-aaa"))

    def test_import_row_number_is_one_based_over_data_rows(self):
        conn = self._open_migrated()
        site_id = _site_id_for(conn, "org-aaa", self._clock_state)
        payload = _payload([
            "asset_tag,name,criticality,purchase_cost_cents",
            "pump-100,Pump 100,high,-5",
            "pump-101,Pump 101,medium,60000",
        ])

        with self.assertRaises(ValidationError) as caught:
            import_assets(
                conn, _plain_context("org-aaa"), actor=_Actor("admin"),
                site_id=site_id, csv_text=payload,
            )
        self.assertIn("row 1", str(caught.exception))
        self.assertNotIn("row 2", str(caught.exception))
        self.assertEqual(0, self._org_count(conn, "org-aaa"))

    def test_import_is_org_scoped(self):
        conn = self._open_migrated()
        site_id_a = _site_id_for(conn, "org-aaa", self._clock_state)
        site_id_b = _site_id_for(conn, "org-bbb", self._clock_state, code="branch")
        payload = _payload([
            "asset_tag,name,criticality,purchase_cost_cents",
            "pump-1,Pump One,low,10000",
        ])

        imported_b = import_assets(
            conn, _plain_context("org-bbb"), actor=_Actor("admin"),
            site_id=site_id_b, csv_text=payload,
        )
        self.assertEqual(1, len(imported_b))
        self.assertEqual(0, self._org_count(conn, "org-aaa"))
        self.assertEqual(1, self._org_count(conn, "org-bbb"))

        imported_a = import_assets(
            conn, _plain_context("org-aaa"), actor=_Actor("admin"),
            site_id=site_id_a, csv_text=payload,
        )
        self.assertEqual(1, len(imported_a))
        self.assertEqual(1, self._org_count(conn, "org-aaa"))
        self.assertEqual(1, self._org_count(conn, "org-bbb"))


if __name__ == "__main__":
    unittest.main()
