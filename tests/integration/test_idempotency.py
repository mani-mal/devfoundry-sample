"""Integration tests (T037, M5): idempotency record core and digest conflicts.

Applies the REAL shipped migrations to a temporary file database and
exercises the idempotency core through public service functions only.
Acceptance (spec M5/T037): a concurrent same-key command causes one
business effect; the same key with a different payload is a 409 conflict
and the original effect is preserved; replaying the same key with the
same payload returns the original result.
"""

import json
import tempfile
import threading
import unittest
from datetime import datetime, timezone

from opsledger.core import OrganizationContext
from opsledger.core.clock import FixedClock
from opsledger.core.db import connect
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError
from opsledger.core.migrations import migrate
from opsledger.core import (
    begin_idempotency,
    canonical_request_digest,
    complete_idempotency,
    fail_idempotency,
    get_idempotency_record,
)


class IdempotencyTest(unittest.TestCase):
    def _open_migrated(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db_path = tmp.name
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

    def _context(self, organization_id="org-aaa", actor_id="user-111"):
        return OrganizationContext(organization_id=organization_id, actor_id=actor_id)

    def _tick_clock(self):
        self._tick = getattr(self, "_tick", 0) + 1
        return FixedClock(datetime(2026, 11, 13, 12, self._tick, 0, tzinfo=timezone.utc))

    def _count_records(self, conn):
        return conn.execute("SELECT COUNT(*) FROM idempotency_records").fetchone()[0]

    def test_t1_begin_complete_and_replay_returns_original_result(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        context = self._context()
        record, replayed = begin_idempotency(
            conn, context, operation="receive_order", key="rcpt-42",
            request_payload={"receipt_id": "rcpt-42", "quantity": 4},
            clock=self._tick_clock(),
        )
        self.assertFalse(replayed)
        self.assertEqual("pending", record["status"])
        self.assertIsNone(record["result_payload"])
        self.assertEqual(
            canonical_request_digest({"receipt_id": "rcpt-42", "quantity": 4}),
            record["request_digest"],
        )
        completed = complete_idempotency(
            conn, context, record_id=record["id"],
            result_payload={"received": 4, "status": "received"},
            clock=self._tick_clock(),
        )
        self.assertEqual("completed", completed["status"])
        self.assertEqual(
            {"received": 4, "status": "received"},
            json.loads(completed["result_payload"]),
        )
        replay_record, replayed = begin_idempotency(
            conn, context, operation="receive_order", key="rcpt-42",
            request_payload={"quantity": 4, "receipt_id": "rcpt-42"},
            clock=self._tick_clock(),
        )
        self.assertTrue(replayed)
        self.assertEqual(record["id"], replay_record["id"])
        self.assertEqual("completed", replay_record["status"])
        self.assertEqual(
            {"received": 4, "status": "received"},
            json.loads(replay_record["result_payload"]),
        )
        self.assertEqual(1, self._count_records(conn))

    def test_t2_same_key_different_payload_is_conflict_409(self):
        conn = self._open_migrated()
        self._seed_organizations(conn)
        context = self._context()
        record, replayed = begin_idempotency(
            conn, context, operation="receive_order", key="rcpt-42",
            request_payload={"receipt_id": "rcpt-42", "quantity": 4},
            clock=self._tick_clock(),
        )
        self.assertFalse(replayed)
        with self.assertRaises(ConflictError) as caught:
            begin_idempotency(
                conn, context, operation="receive_order", key="rcpt-42",
                request_payload={"receipt_id": "rcpt-42", "quantity": 5},
                clock=self._tick_clock(),
            )
        self.assertEqual("conflict", caught.exception.code)
        self.assertEqual(
            "idempotency key already used with a different request payload",
            str(caught.exception),
        )
        after = get_idempotency_record(conn, context, record_id=record["id"])
        self.assertEqual(
            ("pending", record["request_digest"]),
            (after["status"], after["request_digest"]),
        )
        self.assertEqual(1, self._count_records(conn))
