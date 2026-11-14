"""Integration tests (T025b): work-order create service.

These tests apply the REAL shipped migrations to a temporary file database
and then exercise :func:`opsledger.workorders.create_work_order` against
that migrated schema — no CREATE TABLE anywhere in the test. Acceptance
(spec M4/T025): asset, site and requester context consistent — the create
is scoped to an owned site and its asset, duplicates are per organization,
and missing/cross-organization references surface the same NotFoundError.
"""

import tempfile
import unittest
from datetime import datetime, timezone

from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError
from opsledger.core.migrations import migrate
from opsledger.assets import create_asset, create_site
from opsledger.workorders import (
    DUPLICATE_WORK_ORDER_NUMBER_MESSAGE,
    create_work_order,
)


class WorkOrderCreateTests(unittest.TestCase):
    """Integration tests for create_work_order on the real migrated schema."""

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

    def _context(self, organization_id):
        return OrganizationContext(organization_id=organization_id)
