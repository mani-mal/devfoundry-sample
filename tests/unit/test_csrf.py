"""Unit tests for the CSRF context domain module (T011 part A)."""

import unittest
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from opsledger.core.errors import ValidationError
from opsledger.identity.csrf import (
    CSRF_TTL_SECONDS,
    MAX_CSRF_TTL_SECONDS,
    CsrfContext,
    issue_context,
    rotate_context,
    supersede,
    verify_csrf,
    from_row,
    origin_allowed,
    to_row,
)

_BASE_INSTANT = datetime(2026, 11, 6, 12, 0, 0, tzinfo=timezone.utc)


class _StubClock:
    """Deterministic clock stub whose instant the test moves explicitly."""

    def __init__(self, instant: datetime) -> None:
        self._instant = instant.astimezone(timezone.utc)

    def set(self, instant: datetime) -> None:
        self._instant = instant.astimezone(timezone.utc)

    def now(self) -> datetime:
        return self._instant

    def timestamp(self) -> str:
        moment = self._instant.replace(microsecond=0)
        return f"{moment.year:04d}-{moment.month:02d}-{moment.day:02d}T{moment.hour:02d}:{moment.minute:02d}:{moment.second:02d}Z"


class _StubRng:
    """Counter-based rng stub: each call returns distinct 32 bytes."""

    def __init__(self) -> None:
        self._counter = 0

    def __call__(self) -> bytes:
        self._counter += 1
        return bytes([self._counter % 256]) * 32


class IssueVerifyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = _StubClock(_BASE_INSTANT)
        self.rng = _StubRng()

    def test_t1_issued_context_verifies_with_its_raw_token(self) -> None:
        raw_token, context = issue_context(clock=self.clock, rng=self.rng)
        self.assertTrue(verify_csrf(raw_token, context, clock=self.clock))
        self.assertFalse(verify_csrf("definitely-not-the-token", context, clock=self.clock))

    def test_t4_raw_token_absent_from_record_to_row_and_repr(self) -> None:
        raw_token, context = issue_context(clock=self.clock, rng=self.rng)
        self.assertNotIn(raw_token, asdict(context).values())
        self.assertNotIn(raw_token, asdict(context).keys())
        row = to_row(context)
        self.assertNotIn(raw_token, row.values())
        self.assertNotIn(raw_token, repr(context))

    def test_t5_two_issued_contexts_have_different_tokens_and_hashes(self) -> None:
        first_raw, first_context = issue_context(clock=self.clock, rng=self.rng)
        second_raw, second_context = issue_context(clock=self.clock, rng=self.rng)
        self.assertNotEqual(first_raw, second_raw)
        self.assertNotEqual(first_context.token_hash, second_context.token_hash)


class ExpiryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = _StubClock(_BASE_INSTANT)
        self.raw, self.context = issue_context(clock=self.clock, rng=_StubRng())

    def test_t2_expired_context_denied(self) -> None:
        self.clock.set(_BASE_INSTANT + timedelta(seconds=CSRF_TTL_SECONDS))
        self.assertFalse(verify_csrf(self.raw, self.context, clock=self.clock))
        self.clock.set(_BASE_INSTANT + timedelta(seconds=CSRF_TTL_SECONDS - 1))
        self.assertTrue(verify_csrf(self.raw, self.context, clock=self.clock))

    def test_t3_superseded_context_denied_and_supersede_is_idempotent(self) -> None:
        first_supersede_instant = _BASE_INSTANT + timedelta(seconds=5)
        self.clock.set(first_supersede_instant)
        superseded = supersede(self.context, clock=self.clock)
        self.assertIsNotNone(superseded.rotated_at)
        self.assertFalse(verify_csrf(self.raw, superseded, clock=self.clock))
        self.clock.set(_BASE_INSTANT + timedelta(seconds=9))
        second_superseded = supersede(superseded, clock=self.clock)
        self.assertEqual(second_superseded.rotated_at, superseded.rotated_at)


class ShapeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = _StubClock(_BASE_INSTANT)

    def test_t6_token_hash_is_64_lowercase_hex_and_ttl_is_honored(self) -> None:
        _, context = issue_context(clock=self.clock, rng=_StubRng())
        self.assertEqual(len(context.token_hash), 64)
        self.assertTrue(set(context.token_hash) <= set("0123456789abcdef"))
        _, bounded = issue_context(
            clock=self.clock, ttl_seconds=300, rng=_StubRng()
        )
        self.assertEqual(bounded.expires_at - bounded.created_at, timedelta(seconds=300))
        self.assertEqual(CSRF_TTL_SECONDS, 900)
        self.assertEqual(MAX_CSRF_TTL_SECONDS, 3600)

    def test_t7_to_row_from_row_round_trip_and_bad_rows_rejected(self) -> None:
        _, context = issue_context(clock=self.clock, rng=_StubRng())
        row = to_row(context)
        restored = from_row(restored_row := dict(row))
        self.assertEqual(asdict(restored), asdict(context))
        del restored
        too_short = dict(row, token_hash=row["token_hash"][:-1])
        not_hex = dict(row, token_hash="x" * 64)
        missing = {key: value for key, value in row.items() if key != "created_at"}
        for bad_row in (too_short, not_hex, missing):
            with self.assertRaises(ValidationError):
                from_row(bad_row)

    def test_t8_ttl_above_maximum_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            issue_context(clock=self.clock, ttl_seconds=MAX_CSRF_TTL_SECONDS + 1)

    def test_t9_ttl_below_one_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            issue_context(clock=self.clock, ttl_seconds=0)


class RotationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = _StubClock(_BASE_INSTANT)
        self.previous_raw, self.previous = issue_context(clock=self.clock, rng=_StubRng())

    def test_t10_rotation_issues_fresh_pair_and_invalidates_previous(self) -> None:
        self.clock.set(_BASE_INSTANT + timedelta(seconds=3))
        fresh_raw, fresh_context = rotate_context(self.previous, clock=self.clock)
        self.assertNotEqual(fresh_raw, self.previous_raw)
        self.assertNotEqual(fresh_raw, "")
        self.assertTrue(verify_csrf(fresh_raw, fresh_context, clock=self.clock))
        with self.assertRaises(ValidationError):
            expired = CsrfContext(
                token_hash=self.previous.token_hash,
                created_at=_BASE_INSTANT,
                expires_at=_BASE_INSTANT,
            )
            rotate_context(expired, clock=self.clock)
        already_rotated = supersede(self.previous, clock=self.clock)
        with self.assertRaises(ValidationError):
            rotate_context(already_rotated, clock=self.clock)
        self.assertFalse(verify_csrf(self.previous_raw, already_rotated, clock=self.clock))


class OriginAllowedTest(unittest.TestCase):
    def test_t11_same_host_and_port_allowed_but_other_port_or_host_denied(self) -> None:
        self.assertTrue(origin_allowed("http://127.0.0.1:8080", "127.0.0.1:8080"))
        self.assertFalse(origin_allowed("http://127.0.0.1:8080", "127.0.0.1:9090"))
        self.assertFalse(origin_allowed("http://example.com", "other.com"))
        self.assertTrue(origin_allowed("http://Example.COM:8080", "example.com:8080"))

    def test_t12_malformed_origins_all_denied(self) -> None:
        for bad_origin in (None, "", 42, "not a url", "ftp://host:30861", "http://:30861"):
            self.assertFalse(origin_allowed(bad_origin, "127.0.0.1:30861"))


if __name__ == "__main__":
    unittest.main()
