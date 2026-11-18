"""Integration tests for the T062 read-only audit queries.

These tests apply the REAL shipped migrations to a temporary file database
and then exercise ``opsledger.audit.queries.query_events`` and
``opsledger.audit.queries.count_events`` against that migrated schema —
no CREATE TABLE anywhere, mirroring the migrate-a-temp-db setup style.
Every behaviour and boundary is covered: the "audit.read" permission gate
before any query, the malformed authorization context (an actor without a
known role), the optional filter validation and its boundaries, the
machine-verified fixture totals, details parsing to a dict, the limit
bounds, and organization scoping with no cross-org leakage.
"""

import os
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from opsledger.audit.events import record_event
from opsledger.audit.queries import count_events, query_events
from opsledger.core.clock import FixedClock
from opsledger.core.context import OrganizationContext
from opsledger.core.db import connect, transaction
from opsledger.core.errors import PermissionDeniedError, ValidationError
from opsledger.core.migrations import migrate


@dataclass(frozen=True)
class ReportingContext(OrganizationContext):
    """Audit context: an OrganizationContext carrying one role."""

    role: str = "auditor"


class AuditQueryTests(unittest.TestCase):
    """Integration tests for query_events()/count_events() on the real schema."""

    def setUp(self):
        self._clock_tick = 0

    def _open_migrated(self):
        """Open a temporary file database with the REAL shipped migrations."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda p=tmp.name: os.path.exists(p) and os.unlink(p))
        self.addCleanup(lambda: connect(tmp.name).close())
        conn = connect(tmp.name)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def _seed_organization(self, conn, organization_id):
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

    def _tick(self):
        """Each call returns a NEW clock one second later."""
        self._clock_tick += 1
        return FixedClock(
            datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)
            + timedelta(seconds=self._clock_tick)
        )

    def _seed_events(self, conn, organization_id, actor_id):
        """Seed the fixture events: two site ops plus one asset op."""
        self._seed_organization(conn, organization_id)
        context = ReportingContext(organization_id=organization_id, actor_id=actor_id)
        record_event(
            conn,
            context,
            entity_type="site",
            entity_id="site-gamma",
            operation="site.created",
            details={"code": "gamma", "name": "Gamma site"},
            clock=self._tick(),
        )
        record_event(
            conn,
            context,
            entity_type="site",
            entity_id="site-gamma",
            operation="site.renamed",
            details={"name": "Gamma works"},
            clock=self._tick(),
        )
        record_event(
            conn,
            context,
            entity_type="asset",
            entity_id="fan-001",
            operation="asset.noted",
            details={"note": "bearing hum"},
            clock=self._tick(),
        )
        return context

    def test_audit_queries_require_audit_read_permission(self):
        conn = self._open_migrated()
        context = self._seed_events(conn, "org-aaa", "user-111")

        with self.assertRaises(PermissionDeniedError):
            query_events(
                conn,
                context,
                actor=ReportingContext(organization_id="org-aaa", role="supervisor"),
            )
        self.assertEqual(
            3,
            len(
                query_events(
                    conn,
                    context,
                    actor=ReportingContext(organization_id="org-aaa", role="admin"),
                )
            ),
        )
        self.assertEqual(
            3,
            len(
                query_events(
                    conn,
                    context,
                    actor=ReportingContext(organization_id="org-aaa", role="auditor"),
                )
            ),
        )

        with self.assertRaises(ValidationError):
            query_events(
                conn,
                context,
                actor=OrganizationContext(organization_id="org-aaa"),
            )

    def test_filter_validation(self):
        conn = self._open_migrated()
        context = self._seed_events(conn, "org-aaa", "user-111")
        actor = ReportingContext(organization_id="org-aaa", role="admin")

        with self.assertRaises(ValidationError):
            query_events(conn, context, actor=actor, entity_type=42)
        with self.assertRaises(ValidationError):
            query_events(conn, context, actor=actor, entity_type="")
        self.assertEqual(
            3, len(query_events(conn, context, actor=actor, operation=None))
        )
        with self.assertRaises(ValidationError):
            query_events(conn, context, actor=actor, limit=0)
        with self.assertRaises(ValidationError):
            query_events(conn, context, actor=actor, limit=201)
        with self.assertRaises(ValidationError):
            query_events(conn, context, actor=actor, limit=True)
        self.assertEqual(
            3, len(query_events(conn, context, actor=actor, limit=200))
        )

    def test_query_counts_from_machine_verified_fixture(self):
        conn = self._open_migrated()
        context = self._seed_events(conn, "org-aaa", "user-111")
        auditor = ReportingContext(organization_id="org-aaa", role="auditor")

        self.assertEqual(3, count_events(conn, context, actor=auditor))
        self.assertEqual(
            2, count_events(conn, context, actor=auditor, entity_type="site")
        )
        self.assertEqual(
            1, count_events(conn, context, actor=auditor, entity_type="asset")
        )
        self.assertEqual(
            3, count_events(conn, context, actor=auditor, actor_id="user-111")
        )
        self.assertEqual(
            1, count_events(conn, context, actor=auditor, operation="site.created")
        )
        self.assertEqual(
            0, count_events(conn, context, actor=auditor, entity_type="work_order")
        )

    def test_query_returns_parsed_details_in_history_order(self):
        conn = self._open_migrated()
        context = self._seed_events(conn, "org-aaa", "user-111")
        auditor = ReportingContext(organization_id="org-aaa", role="auditor")

        rows = query_events(conn, context, actor=auditor, entity_type="site")

        self.assertEqual(2, len(rows))
        for row in rows:
            self.assertIsInstance(row, dict)
            self.assertEqual(
                [
                    "id",
                    "actor_id",
                    "entity_type",
                    "entity_id",
                    "operation",
                    "details",
                    "created_at",
                ],
                list(row),
            )
            self.assertIsInstance(row["details"], dict)
        self.assertEqual("site.created", rows[0]["operation"])
        self.assertEqual("site.renamed", rows[1]["operation"])
        self.assertLessEqual(rows[0]["created_at"], rows[1]["created_at"])

    def test_query_limit_bounds_the_result(self):
        conn = self._open_migrated()
        context = self._seed_events(conn, "org-aaa", "user-111")
        auditor = ReportingContext(organization_id="org-aaa", role="auditor")

        rows = query_events(conn, context, actor=auditor, limit=2)

        self.assertEqual(2, len(rows))
        self.assertEqual("site.created", rows[0]["operation"])
        self.assertEqual("site.renamed", rows[1]["operation"])

    def test_audit_queries_are_org_scoped_no_leak(self):
        conn = self._open_migrated()
        org_aaa = self._seed_events(conn, "org-aaa", "user-111")
        org_bbb = self._seed_events(conn, "org-bbb", "user-222")
        auditor = ReportingContext(organization_id="org-aaa", role="auditor")

        self.assertEqual(3, count_events(conn, org_aaa, actor=auditor))
        self.assertEqual(
            [], query_events(conn, org_aaa, actor=auditor, entity_id="fan-777")
        )
        self.assertEqual(
            0, count_events(conn, org_aaa, actor=auditor, entity_id="fan-777")
        )
        self.assertEqual(3, count_events(conn, org_bbb, actor=auditor))

    def test_combined_filters_and_combine(self):
        conn = self._open_migrated()
        context = self._seed_events(conn, "org-aaa", "user-111")
        auditor = ReportingContext(organization_id="org-aaa", role="auditor")

        rows = query_events(
            conn, context, actor=auditor, entity_type="site", operation="site.created"
        )

        self.assertEqual(1, len(rows))
        self.assertEqual("site.created", rows[0]["operation"])
