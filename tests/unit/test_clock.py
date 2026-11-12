"""Tests for the UTC clocks and RFC3339 Z serialization (T001)."""

import sys
import pathlib
import unittest
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from opsledger.core.clock import (  # noqa: E402
    FixedClock,
    RealClock,
    format_rfc3339,
    require_aware_utc,
)
from opsledger.core.errors import ValidationError  # noqa: E402

FIXED_INSTANT = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


class RealClockTests(unittest.TestCase):
    def test_now_is_timezone_aware_utc(self):
        now = RealClock().now()
        self.assertIsNotNone(now.tzinfo)
        self.assertEqual(now.utcoffset(), timedelta(0))

    def test_timestamp_ends_in_z_at_second_precision(self):
        stamp = RealClock().timestamp()
        self.assertRegex(
            stamp, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
        )

    def test_timestamp_is_close_to_utc_wall_clock(self):
        before = datetime.now(timezone.utc).replace(microsecond=0)
        stamp = RealClock().timestamp()
        after = datetime.now(timezone.utc).replace(microsecond=0)
        parsed = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        self.assertTrue(before <= parsed <= after)


class FixedClockTests(unittest.TestCase):
    def test_utc_instant_serializes_with_z_suffix(self):
        clock = FixedClock(FIXED_INSTANT)
        self.assertEqual(clock.timestamp(), "2026-01-01T00:00:00Z")

    def test_offset_instant_normalizes_to_utc_z(self):
        plus_three = timezone(timedelta(hours=3))
        clock = FixedClock(datetime(2026, 1, 1, 3, 0, 0, tzinfo=plus_three))
        self.assertEqual(clock.timestamp(), "2026-01-01T00:00:00Z")

    def test_microseconds_are_truncated(self):
        clock = FixedClock(
            datetime(2026, 1, 1, 0, 0, 0, 999999, tzinfo=timezone.utc)
        )
        self.assertEqual(clock.timestamp(), "2026-01-01T00:00:00Z")

    def test_repeated_reads_are_identical(self):
        clock = FixedClock(FIXED_INSTANT)
        first = clock.now()
        second = clock.now()
        self.assertEqual(first, second)
        self.assertEqual(clock.timestamp(), clock.timestamp())

    def test_now_is_timezone_aware_utc(self):
        now = FixedClock(FIXED_INSTANT).now()
        self.assertIsNotNone(now.tzinfo)
        self.assertEqual(now.utcoffset(), timedelta(0))


class Rfc3339SerializationTests(unittest.TestCase):
    def test_utc_datetime_serializes_with_z(self):
        stamp = format_rfc3339(FIXED_INSTANT)
        self.assertEqual(stamp, "2026-01-01T00:00:00Z")

    def test_non_utc_datetime_normalizes_to_utc(self):
        minus_five = timezone(timedelta(hours=-5))
        stamp = format_rfc3339(datetime(2026, 1, 1, 5, 0, 0, tzinfo=minus_five))
        self.assertEqual(stamp, "2026-01-01T10:00:00Z")

    def test_naive_datetime_is_rejected(self):
        with self.assertRaises(ValidationError) as caught:
            format_rfc3339(datetime(2026, 1, 1, 0, 0, 0))
        self.assertEqual(caught.exception.code, "validation_error")

    def test_require_aware_utc_returns_utc_value(self):
        value = require_aware_utc(FIXED_INSTANT)
        self.assertEqual(value, FIXED_INSTANT)
        self.assertEqual(value.utcoffset(), timedelta(0))

    def test_require_aware_utc_rejects_naive(self):
        with self.assertRaises(ValidationError):
            require_aware_utc(datetime(2026, 1, 1, 0, 0, 0))

    def test_years_below_1000_are_zero_padded(self):
        cases = {
            1: "0001-06-15T12:34:56Z",
            99: "0099-06-15T12:34:56Z",
            999: "0999-06-15T12:34:56Z",
        }
        for year, expected in cases.items():
            stamp = format_rfc3339(
                datetime(year, 6, 15, 12, 34, 56, tzinfo=timezone.utc)
            )
            self.assertEqual(stamp, expected)
        self.assertEqual(
            format_rfc3339(
                datetime(2026, 6, 15, 12, 34, 56, tzinfo=timezone.utc)
            ),
            "2026-06-15T12:34:56Z",
        )


if __name__ == "__main__":
    unittest.main()
