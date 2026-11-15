"""Integration tests (T030b): work-order comment service.

These tests apply the REAL shipped migrations to a temporary file database
and then exercise :mod:`opsledger.workorders.comments` against that
migrated schema — no CREATE TABLE anywhere in the test. Acceptance (spec
M4/T030): user text is literal (formula prefixes are data, not commands);
the author identity comes from the caller, not from the body; comments
anchor to the work order's aggregate version at write time and are
immutable.
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
from opsledger.workorders import create_work_order
from opsledger.workorders.comments import (
    BODY_MESSAGE,
    add_comment,
    list_comments,
)


class CommentTests(unittest.TestCase):
    """Integration tests for the comment service on the real migrated schema."""

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

    def _clock(self, hour=12):
        return FixedClock(datetime(2026, 11, 13, hour, 0, 0, tzinfo=timezone.utc))

    def _seed_work_order(self, conn, number="wo-100"):
        clock = self._clock()
        self._seed_organizations(conn)
        site_a = create_site(conn, self._context(), code="main", name="Site A", clock=clock)
        site_b = create_site(conn, self._context("org-bbb"), code="main", name="Site B", clock=clock)
        asset_a = create_asset(
            conn, self._context(), site_id=site_a["id"], tag="pump-001",
            name="Asset pump-001", criticality="medium", purchase_cost_cents=10000, clock=clock,
        )
        work_order = create_work_order(
            conn, self._context(), site_id=site_a["id"], asset_id=asset_a["id"],
            number=number, title="Rebuild pump", description="Full rebuild",
            priority="high", requester_id="user-111", clock=clock,
        )
        return site_a, site_b, work_order

    def _comment(self, conn, work_order, body, author_id="user-111", hour=15):
        return add_comment(
            conn, self._context(), work_order_id=work_order["id"], author_id=author_id,
            body=body, clock=FixedClock(datetime(2026, 11, 13, hour, 0, 0, tzinfo=timezone.utc)),
        )

    def test_t1_add_comment_anchors_current_version(self):
        conn = self._open_migrated()
        _, _, work_order = self._seed_work_order(conn)
        comment = self._comment(conn, work_order, "started inspection")
        self.assertEqual("cmt-", comment["id"][:4])
        self.assertEqual(1, comment["at_version"])
        self.assertEqual("user-111", comment["author_id"])

    def test_t2_user_text_is_literal(self):
        conn = self._open_migrated()
        _, _, work_order = self._seed_work_order(conn)
        comment = self._comment(conn, work_order, "=SUM(A1)+cmd|danger")
        self.assertEqual("=SUM(A1)+cmd|danger", comment["body"])
        stored = conn.execute("SELECT body FROM comments WHERE id = ?", (comment["id"],)).fetchone()
        self.assertEqual("=SUM(A1)+cmd|danger", stored["body"])

    def test_t3_blank_body_refused(self):
        conn = self._open_migrated()
        _, _, work_order = self._seed_work_order(conn)
        with self.assertRaises(ValidationError) as caught:
            self._comment(conn, work_order, "   ")
        self.assertEqual(BODY_MESSAGE, str(caught.exception))

    def test_t4_non_string_body_refused(self):
        conn = self._open_migrated()
        _, _, work_order = self._seed_work_order(conn)
        with self.assertRaises(ValidationError):
            add_comment(
                conn, self._context(), work_order_id=work_order["id"], author_id="user-111",
                body=123, clock=self._clock(),
            )
