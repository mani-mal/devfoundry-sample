"""Core foundation for OpsLedger services (T001, T002).

Ships the shared application error types, the UTC clocks, and the SQLite
connection factory and transaction context used by every later business
module.
"""

from .clock import (
    Clock,
    FixedClock,
    RFC3339_Z_FORMAT,
    RealClock,
    format_rfc3339,
    require_aware_utc,
)
from .errors import (
    ApplicationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from .db import connect, transaction

__all__ = [
    "ApplicationError",
    "Clock",
    "ConflictError",
    "connect",
    "FixedClock",
    "NotFoundError",
    "PermissionDeniedError",
    "RFC3339_Z_FORMAT",
    "RealClock",
    "ValidationError",
    "transaction",
    "format_rfc3339",
    "require_aware_utc",
]
