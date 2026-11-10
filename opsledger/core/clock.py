"""UTC clocks for OpsLedger: a real wall clock and a fixed clock for tests.

All clock values are timezone-aware UTC datetimes. Serialization is
canonical second-precision RFC3339 ending in ``Z`` (never an offset such as
``+00:00``, never local time).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from .errors import ValidationError

__all__ = [
    "Clock",
    "FixedClock",
    "RFC3339_Z_FORMAT",
    "RealClock",
    "format_rfc3339",
    "require_aware_utc",
]

RFC3339_Z_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class Clock(Protocol):
    """Anything that can tell time for the application."""

    def now(self) -> datetime:
        """Current time as a timezone-aware UTC datetime."""
        ...

    def timestamp(self) -> str:
        """Current time as canonical second-precision RFC3339 ``Z`` text."""
        ...


def require_aware_utc(value: datetime) -> datetime:
    """Return ``value`` normalized to timezone-aware UTC.

    Naive datetimes are rejected with :class:`ValidationError`; aware
    non-UTC values are converted to UTC.
    """
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValidationError("datetime must be timezone-aware UTC")
    return value.astimezone(timezone.utc)


def format_rfc3339(value: datetime) -> str:
    """Serialize an aware datetime as second-precision RFC3339 ending in Z."""
    normalized = require_aware_utc(value).replace(microsecond=0)
    return normalized.strftime(RFC3339_Z_FORMAT)


class RealClock:
    """Wall clock: always reports timezone-aware UTC, never local time."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def timestamp(self) -> str:
        return format_rfc3339(self.now())


class FixedClock:
    """Deterministic clock for tests: always returns one fixed UTC instant.

    The instant is normalized to UTC and truncated to second precision at
    construction, so repeated reads are identical.
    """

    def __init__(self, instant: datetime) -> None:
        self._instant = require_aware_utc(instant).replace(microsecond=0)

    def now(self) -> datetime:
        return self._instant

    def timestamp(self) -> str:
        return format_rfc3339(self._instant)
