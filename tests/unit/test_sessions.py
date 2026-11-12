"""Unit tests for the session domain module (T010-A)."""

from __future__ import annotations

import dataclasses
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from opsledger.identity import (  # noqa: E402
    MAX_SESSION_TTL_SECONDS,
    SESSION_TTL_SECONDS,
    SessionRecord,
    create_session,
    from_session_row,
    to_session_row,
)
from opsledger.identity.sessions import revoke_session, verify_session  # noqa: E402
from opsledger.core.errors import ValidationError  # noqa: E402

UTC = timezone.utc
INSTANT = datetime(2026, 11, 6, 12, 0, 0, tzinfo=UTC)
HEX_DIGITS = set("0123456789abcdef")


class StubClock:
    """Fixed timezone-aware UTC clock stub."""

    def __init__(self, instant: datetime) -> None:
        self._instant = instant.astimezone(UTC).replace(microsecond=0)

    def now(self) -> datetime:
        return self._instant

    def timestamp(self) -> str:
        normalized = self._instant
        return (
            f"{normalized.year:04d}-{normalized.month:02d}-{normalized.day:02d}"
            f"T{normalized.hour:02d}:{normalized.minute:02d}"
            f":{normalized.second:02d}Z"
        )


class StubRng:
    """Deterministic injectable rng returning one distinct pattern per call."""

    def __init__(self, base: bytes = b"stub-token-bytes------------") -> None:
        self.base = base
        self.calls = 0

    def __call__(self) -> bytes:
        self.calls += 1
        return self.base + bytes([self.calls])


class TestSessions(unittest.TestCase):
    def session(
        self,
        user_id: str = "user-1",
        *,
        clock: StubClock | None = None,
        ttl_seconds: int = SESSION_TTL_SECONDS,
        rng: StubRng | None = None,
    ) -> tuple[str, SessionRecord]:
        clock = clock if clock is not None else StubClock(INSTANT)
        return create_session(
            user_id, clock=clock, ttl_seconds=ttl_seconds, rng=rng
        )

    def test_t1_created_session_verifies_with_raw_token_and_other_fails(self):
        clock = StubClock(INSTANT)
        raw, record = self.session(clock=clock)
        self.assertIs(verify_session(raw, record, clock=clock), True)
        different = "different-token-value-not-the-presented-one!!!!"
        self.assertIs(verify_session(different, record, clock=clock), False)

    def test_t2_expired_session_denied(self):
        clock = StubClock(INSTANT)
        raw, record = self.session(clock=clock)
        after = StubClock(record.expires_at + timedelta(seconds=1))
        self.assertIs(verify_session(raw, record, clock=after), False)
        exact = StubClock(record.expires_at)
        self.assertIs(verify_session(raw, record, clock=exact), False)
        just_before = StubClock(record.expires_at - timedelta(seconds=1))
        self.assertIs(verify_session(raw, record, clock=just_before), True)

    def test_t3_revoked_session_denied_and_revoke_idempotent(self):
        clock = StubClock(INSTANT)
        raw, record = self.session(clock=clock)
        revoked = revoke_session(record, clock=clock)
        self.assertIsNotNone(revoked.revoked_at)
        self.assertIs(verify_session(raw, revoked, clock=clock), False)
        later = StubClock(INSTANT + timedelta(hours=8))
        again = revoke_session(revoked, clock=later)
        self.assertIs(again, revoked)
        self.assertEqual(again.revoked_at, revoked.revoked_at)

    def test_t4_raw_token_absent_from_record_fields_row_and_repr(self):
        raw, record = self.session()
        field_names = [f.name for f in dataclasses.fields(record)]
        self.assertNotIn("token", field_names)
        self.assertNotIn("raw_token", field_names)
        row = to_session_row(record)
        self.assertNotIn("token", row)
        self.assertNotIn("raw_token", row)
        rendered = repr(record)
        self.assertNotIn(raw, rendered)
        self.assertNotIn(raw, str(row))
        self.assertEqual(row["token_hash"], record.token_hash)

    def test_t5_two_sessions_for_one_user_differ(self):
        clock = StubClock(INSTANT)
        rng = StubRng()
        first_raw, first_record = self.session(user_id="user-1", clock=clock, rng=rng)
        second_raw, second_record = self.session(user_id="user-1", clock=clock, rng=rng)
        self.assertNotEqual(first_raw, second_raw)
        self.assertNotEqual(first_record.token_hash, second_record.token_hash)

    def test_t6_token_hash_shape_and_ttl(self):
        raw, record = self.session()
        self.assertEqual(len(record.token_hash), 64)
        self.assertTrue(set(record.token_hash) <= HEX_DIGITS)
        self.assertEqual(record.token_hash, record.token_hash.lower())
        self.assertNotEqual(record.token_hash, raw)
        self.assertEqual(
            record.expires_at - record.created_at,
            timedelta(seconds=SESSION_TTL_SECONDS),
        )

    def test_t7_row_round_trip_and_bad_rows_rejected(self):
        clock = StubClock(INSTANT)
        raw, record = self.session(clock=clock)
        row = to_session_row(record)
        rebuilt = from_session_row(row)
        self.assertEqual(rebuilt, record)
        self.assertIs(verify_session(raw, rebuilt, clock=clock), True)
        bad_len = dict(row, token_hash="abc" * 20)
        with self.assertRaises(ValidationError):
            from_session_row(bad_len)
        bad_hex = dict(row, token_hash="z" * 64)
        with self.assertRaises(ValidationError):
            from_session_row(bad_hex)
        missing = {k: v for k, v in row.items() if k != "user_id"}
        with self.assertRaises(KeyError):
            from_session_row(missing)

    def test_t8_ttl_above_maximum_rejected(self):
        with self.assertRaises(ValidationError):
            create_session(
                "user-1",
                clock=StubClock(INSTANT),
                ttl_seconds=MAX_SESSION_TTL_SECONDS + 1,
            )

    def test_t9_ttl_below_one_rejected(self):
        with self.assertRaises(ValidationError):
            create_session("user-1", clock=StubClock(INSTANT), ttl_seconds=0)
        with self.assertRaises(ValidationError):
            create_session("user-1", clock=StubClock(INSTANT), ttl_seconds=-1)

    def test_t10_verify_non_str_token_rejected(self):
        clock = StubClock(INSTANT)
        raw, record = self.session(clock=clock)
        for bad in (None, 123, b"bytes-token", ["list-token"]):
            with self.assertRaises(ValidationError):
                verify_session(bad, record, clock=clock)
        self.assertIs(verify_session(raw, record, clock=clock), True)


if __name__ == "__main__":
    unittest.main()
