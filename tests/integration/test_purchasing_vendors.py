"""Integration tests (T041, M6): vendor records.

Applies the REAL shipped migrations to a temporary file database (no
CREATE TABLE) and exercises the vendor service through its public
functions only, with a _tick_clock helper giving each call a DISTINCT
FixedClock timestamp (UTC, RFC3339 Z, second precision).
"""

import os
import tempfile
import unittest
from datetime import datetime, timezone

from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError
from opsledger.core.migrations import migrate
from opsledger.purchasing.vendors import (
    DUPLICATE_VENDOR_NAME_MESSAGE,
    VENDOR_NOT_FOUND_MESSAGE,
    create_vendor,
    get_vendor,
    list_vendors,
)


class VendorsTest(unittest.TestCase):
    def setUp(self):
        self._clock_tick = 0

    def _open_migrated(self):
        """Open a temporary file database with the REAL shipped migrations (no CREATE TABLE)."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda p=tmp.name: os.path.exists(p) and os.unlink(p))
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

    def _tick_clock(self):
        """Each call returns a DISTINCT FixedClock: UTC, RFC3339 Z, seconds."""
        self._clock_tick += 1
        return FixedClock(datetime(2026, 11, 13, 12, 0, self._clock_tick, tzinfo=timezone.utc))

    def _vendor(self, conn, context, name="Acme", contact_email=None):
        return create_vendor(conn, context, name=name, contact_email=contact_email, clock=self._tick_clock())

    def test_t1_create_vendor_and_get_roundtrip(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        vendor = self._vendor(conn, self._context())
        self.assertTrue(vendor["id"].startswith("ven-"))
        self.assertEqual("Acme", vendor["name"])
        self.assertIsNone(vendor["contact_email"])
        self.assertEqual(1, vendor["version"])
        self.assertIsNone(vendor["archived_at"])
        fetched = get_vendor(conn, self._context(), vendor["id"])
        self.assertEqual(vendor["id"], fetched["id"])
        with_email = self._vendor(conn, self._context(), name="Other", contact_email="ops@acme.test")
        self.assertEqual("ops@acme.test", with_email["contact_email"])

    def test_t2_same_org_duplicate_name_rejected(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        self._vendor(conn, self._context())
        with self.assertRaises(ConflictError) as caught:
            self._vendor(conn, self._context())
        self.assertEqual(DUPLICATE_VENDOR_NAME_MESSAGE, str(caught.exception))
        count = conn.execute("SELECT COUNT(*) FROM vendors WHERE name = 'Acme'").fetchone()
        self.assertEqual(1, count[0])

    def test_t3_cross_org_lookup_not_found(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        vendor = self._vendor(conn, self._context())
        with self.assertRaises(NotFoundError) as missing:
            get_vendor(conn, self._context(), "ven-does-not-exist")
        with self.assertRaises(NotFoundError) as cross:
            get_vendor(conn, self._context("org-bbb"), vendor["id"])
        self.assertEqual(VENDOR_NOT_FOUND_MESSAGE, str(missing.exception))
        self.assertEqual(VENDOR_NOT_FOUND_MESSAGE, str(cross.exception))

    def test_t4_validation_rejects_blank_name_and_email(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        with self.assertRaises(ValidationError):
            self._vendor(conn, self._context(), name="")
        with self.assertRaises(ValidationError):
            self._vendor(conn, self._context(), name="   ")
        with self.assertRaises(ValidationError):
            self._vendor(conn, self._context(), contact_email="")
        with self.assertRaises(ValidationError):
            self._vendor(conn, self._context(), contact_email="   ")
        count = conn.execute("SELECT COUNT(*) FROM vendors").fetchone()
        self.assertEqual(0, count[0])

    def test_t5_acceptance_same_name_across_organizations(self):
        """Same-org names are unique: 'Acme' in org-aaa and org-bbb, plus a second org-aaa vendor."""
        conn = self._open_migrated()
        self._seed_organizations(conn)
        first = self._vendor(conn, self._context(), name="Acme")
        second = self._vendor(conn, self._context(), name="Contoso")
        other = self._vendor(conn, self._context("org-bbb"), name="Acme")
        rows = list_vendors(conn, self._context())
        self.assertEqual(2, len(rows))
        self.assertEqual([first["id"], second["id"]], [row["id"] for row in rows])
        other_rows = list_vendors(conn, self._context("org-bbb"))
        self.assertEqual(1, len(other_rows))
        self.assertEqual(other["id"], other_rows[0]["id"])
        with self.assertRaises(ConflictError) as again:
            self._vendor(conn, self._context(), name="Acme")
        self.assertEqual(DUPLICATE_VENDOR_NAME_MESSAGE, str(again.exception))

    def test_t6_list_is_oldest_first(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        first = self._vendor(conn, self._context(), name="A")
        second = self._vendor(conn, self._context(), name="B")
        rows = list_vendors(conn, self._context())
        self.assertEqual([first["id"], second["id"]], [row["id"] for row in rows])


if __name__ == "__main__":
    unittest.main()
