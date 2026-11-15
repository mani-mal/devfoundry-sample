"""Integration tests (T033, M5): parts and stock-location records.

Applies the REAL shipped migrations to a temporary file database (no
CREATE TABLE) and exercises the parts/stock-location services through
their public functions only. Acceptance (spec M5/T033): scoped SKU and
location uniqueness — same SKU/code in another organization is allowed,
same-org duplicates are refused with the canonical message (nothing
stored); cross-organization lookups are indistinguishable from missing
(no existence leak).
"""

import tempfile
import unittest
from datetime import datetime, timezone

from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError
from opsledger.core.migrations import migrate
from opsledger.parts import (
    DUPLICATE_PART_SKU_MESSAGE,
    DUPLICATE_STOCK_LOCATION_CODE_MESSAGE,
    create_part,
    create_stock_location,
    get_part,
    get_stock_location,
    list_parts,
    list_stock_locations,
)


class PartsLocationsTest(unittest.TestCase):
    def _open_migrated(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda: connect(tmp.name).close())
        conn = connect(tmp.name)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def _seed_organizations(self, conn):
        created_text = "2026-11-06T12:00:00Z"
        with conn:
            conn.execute(
                "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                ("org-aaa", "org-aaa", "Organization AAA", created_text),
            )
            conn.execute(
                "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                ("org-bbb", "org-bbb", "Organization BBB", created_text),
            )

    def _context(self, organization_id="org-aaa"):
        return OrganizationContext(organization_id=organization_id)

    def _clock(self):
        return FixedClock(datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc))

    def _part(self, conn, context, sku="bolt-m8", name="M8 bolt", **overrides):
        # Distinct timestamp per create: identical created_at ties are
        # broken by the random id, so tests advance the clock per call
        # to keep (created_at, id) ordering deterministic.
        self._tick = getattr(self, "_tick", 0) + 1
        return create_part(
            conn, context, sku=sku, name=name,
            unit_of_measure=overrides.get("unit_of_measure", "unit"),
            standard_cost_cents=overrides.get("standard_cost_cents", 2500),
            clock=FixedClock(datetime(2026, 11, 13, 12, self._tick, 0, tzinfo=timezone.utc)),
        )

    def _location(self, conn, context, code="main", name="Main store"):
        self._tick = getattr(self, "_tick", 0) + 1
        return create_stock_location(
            conn, context, code=code, name=name,
            clock=FixedClock(datetime(2026, 11, 13, 12, self._tick, 0, tzinfo=timezone.utc)),
        )

    def test_t1_create_part_and_get_roundtrip(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        part = self._part(conn, self._context())
        self.assertEqual("bolt-m8", part["sku"])
        self.assertEqual(2500, part["standard_cost_cents"])
        self.assertEqual(1, part["version"])
        fetched = get_part(conn, self._context(), part["id"])
        self.assertEqual(part["id"], fetched["id"])

    def test_t2_same_org_duplicate_sku_refused_with_nothing_stored(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        self._part(conn, self._context(), sku="bolt-m8")
        with self.assertRaises(ConflictError) as caught:
            self._part(conn, self._context(), sku="bolt-m8")
        self.assertEqual(DUPLICATE_PART_SKU_MESSAGE, str(caught.exception))
        rows = conn.execute(
            "SELECT COUNT(*) FROM parts WHERE sku = 'bolt-m8'"
        ).fetchone()
        self.assertEqual(1, rows[0])

    def test_t3_same_sku_in_other_organization_is_allowed_and_invisible(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        own_part = self._part(conn, self._context(), sku="bolt-m8")
        other = self._part(conn, self._context("org-bbb"), sku="bolt-m8")
        self.assertEqual("bolt-m8", other["sku"])
        self.assertNotEqual(own_part["id"], other["id"])
        own = list_parts(conn, self._context())
        self.assertEqual(1, len(own))
        self.assertEqual(own_part["id"], own[0]["id"])
        other_rows = list_parts(conn, self._context("org-bbb"))
        self.assertEqual(1, len(other_rows))
        self.assertEqual(other["id"], other_rows[0]["id"])
