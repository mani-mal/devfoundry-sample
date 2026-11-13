"""Integration tests (T022 part C): audit_events storage and the
transactional-audit tests.

These tests apply the REAL shipped migrations to a temporary file database and
then exercise :func:`opencode.assets.update_asset_audited` and
:func:`opsledger.audit.events_for_entity` against the migrated schema —
no CREATE TABLE anywhere in the test (the audit_events table comes from the
real migration; t2's DROP TABLE is a drop, not a create). Acceptance
(spec M3/T022): forced audit failure rolls back the business mutation.
"""

import json
import tempfile
import unittest
from datetime import datetime, timezone

from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect
from opsledger.core.errors import ConflictError
from opsledger.core.migrations import migrate
from opsledger.assets import create_asset, create_site
from opsledger.audit import events_for_entity
from opsledger.assets.updates import STALE_VERSION_MESSAGE, update_asset_audited


class AssetAuditTests(unittest.TestCase):
    """Transactional-audit tests against the real migrated schema."""

    def _open_migrated(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.addCleanup(lambda: connect(tmp.name).close())
        conn = connect(tmp.name)
        self.addCleanup(conn.close)
        migrate(conn, "opsledger/migrations")
        return conn

    def _seed(self, conn, tag="pump-100", include_organization=True, code="main"):
        self._custom = {"note": "rebuilt housing", "ticket": "OPS-42"}
        organization = "org-aaa"
        created_text = "2026-11-06T12:00:00Z"
        if include_organization:
            with conn:
                conn.execute(
                    "INSERT INTO organizations (id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                    (organization, organization, "Organization AAA", created_text),
                )
        clock = FixedClock(datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc))
        site = create_site(
            conn,
            self._context(actor_id="actor-aaa"),
            code=code,
            name="Site A",
            clock=clock,
        )
        asset = create_asset(
            conn,
            self._context(actor_id="actor-aaa"),
            site_id=site["id"],
            tag=tag,
            name="Asset " + tag,
            criticality="medium",
            purchase_cost_cents=10000,
            clock=clock,
        )
        return asset

    def _context(self, organization_id="org-aaa", actor_id=None):
        return OrganizationContext(organization_id=organization_id, actor_id=actor_id)

    def test_t1_audited_update_commits_atomically(self):
        conn = self._open_migrated()
        asset = self._seed(conn)
        self.assertEqual(1, asset["version"])
        new_name = "Rebuilt pump"

        winner = update_asset_audited(
            conn,
            self._context(actor_id="actor-aaa"),
            asset_id=asset["id"],
            expected_version=1,
            name=new_name,
            clock=FixedClock(datetime(2026, 11, 13, 15, 0, 0, tzinfo=timezone.utc)),
        )
        self.assertEqual(2, winner["version"])
        self.assertEqual(new_name, winner["name"])

        row = conn.execute(
            "SELECT name, version FROM assets WHERE id = ?", (asset["id"],)
        ).fetchone()
        self.assertEqual(new_name, row["name"])
        self.assertEqual(2, row["version"])

        events = events_for_entity(
            conn, self._context(actor_id="actor-aaa"), entity_type="asset", entity_id=asset["id"]
        )
        self.assertEqual(1, len(events))
        self.assertEqual("asset.update", events[0]["operation"])
        self.assertEqual("actor-aaa", events[0]["actor_id"])
    def test_t2_forced_audit_failure_rolls_back_business_mutation(self):
        conn = self._open_migrated()
        asset = self._seed(conn, tag="pump-101")
        self.assertEqual(1, asset["version"])

        conn.execute("DROP TABLE audit_events")

        with self.assertRaises(Exception):
            update_asset_audited(
                conn,
                self._context(),
                asset_id=asset["id"],
                expected_version=1,
                name="Should never persist",
                clock=FixedClock(datetime(2026, 11, 13, 15, 0, 0, tzinfo=timezone.utc)),
            )

        refetched = conn.execute(
            "SELECT name, version FROM assets WHERE id = ?", (asset["id"],)
        ).fetchone()
        self.assertEqual("Asset pump-101", refetched["name"])
        self.assertEqual(1, refetched["version"])

    def test_t3_stale_version_writes_no_audit_row(self):
        conn = self._open_migrated()
        asset = self._seed(conn, tag="pump-102")
        first = update_asset_audited(
            conn,
            self._context(),
            asset_id=asset["id"],
            expected_version=1,
            name="Renamed once",
            clock=FixedClock(datetime(2026, 11, 13, 15, 0, 0, tzinfo=timezone.utc)),
        )
        self.assertEqual(2, first["version"])

        with self.assertRaises(ConflictError) as caught:
            update_asset_audited(
                conn,
                self._context(),
                asset_id=asset["id"],
                expected_version=1,
                name="Stale writer",
                clock=FixedClock(datetime(2026, 11, 13, 15, 1, 0, tzinfo=timezone.utc)),
            )
        self.assertEqual(STALE_VERSION_MESSAGE, caught.exception.args[0])

        events = events_for_entity(
            conn, self._context(), entity_type="asset", entity_id=asset["id"]
        )
        self.assertEqual(1, len(events))

    def test_t4_audit_details_are_canonical(self):
        conn = self._open_migrated()
        asset = self._seed(conn, tag="pump-103")
        custom = {"note": "rebuilt housing", "ticket": "OPS-42"}
        update_a = update_asset_audited(
            conn,
            self._context(actor_id="actor-aaa"),
            asset_id=asset["id"],
            expected_version=1,
            name="Canonical rename",
            clock=FixedClock(datetime(2026, 11, 13, 15, 0, 0, tzinfo=timezone.utc)),
        )
        self.assertEqual(2, update_a["version"])

        events = events_for_entity(
            conn, self._context(actor_id="actor-aaa"), entity_type="asset", entity_id=asset["id"]
        )
        self.assertEqual(1, len(events))
        details = json.loads(events[0]["details"])
        self.assertIn("fields", details)
        self.assertIn("from_version", details)
        self.assertIn("to_version", details)

        asset_b = self._seed(conn, tag="pump-105", include_organization=False, code="secondary")
        update_b = update_asset_audited(
            conn,
            self._context(actor_id="actor-aaa"),
            asset_id=asset_b["id"],
            expected_version=1,
            name="Custom rename",
            audit_details=custom,
            clock=FixedClock(datetime(2026, 11, 13, 15, 0, 0, tzinfo=timezone.utc)),
        )
        self.assertEqual(2, update_b["version"])
        custom_events = events_for_entity(
            conn, self._context(actor_id="actor-aaa"), entity_type="asset", entity_id=asset_b["id"]
        )
        self.assertEqual(1, len(custom_events))
        self.assertEqual(custom, json.loads(custom_events[0]["details"]))

    def test_t5_events_scoping_and_order(self):
        conn = self._open_migrated()
        asset = self._seed(conn, tag="pump-104")
        for index in range(3):
            update = update_asset_audited(
                conn,
                self._context(),
                asset_id=asset["id"],
                expected_version=expected_value(index),
                name="Name " + str(index),
                clock=FixedClock(
                    datetime(2026, 11, 13, 15, 10 + index, 0, tzinfo=timezone.utc)
                ),
            )
            self.assertEqual(index + 2, update["version"])

        events = events_for_entity(
            conn, self._context(), entity_type="asset", entity_id=asset["id"]
        )
        self.assertEqual(3, len(events))
        self.assertTrue(
            all(event["entity_id"] == asset["id"] for event in events)
        )
        keys = [(event["created_at"], event["created_at"]) for event in events]
        self.assertEqual(keys, sorted(keys))

        foreign_asset = conn.execute(
            "SELECT id FROM assets WHERE id != ?", (asset["id"],)
        ).fetchone()
        self.assertIsNone(foreign_asset)

        empty_events = events_for_entity(
            conn, self._context(), entity_type="asset", entity_id="no-events-entity"
        )
        self.assertEqual([], empty_events)

        foreign_org_events = events_for_entity(
            conn,
            OrganizationContext(organization_id="org-zzz"),
            entity_type="asset",
            entity_id=asset["id"],
        )
        self.assertEqual([], foreign_org_events)


def expected_value(index):
    return index + 1


def _unused():
    return None
