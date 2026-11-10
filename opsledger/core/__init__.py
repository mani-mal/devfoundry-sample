"""Core foundation for OpsLedger services (T001).

Ships the shared application error types and the UTC clocks used by every
later business module.
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

__all__ = [
    "ApplicationError",
    "Clock",
    "ConflictError",
    "FixedClock",
    "NotFoundError",
    "PermissionDeniedError",
    "RFC3339_Z_FORMAT",
    "RealClock",
    "ValidationError",
    "format_rfc3339",
    "require_aware_utc",
]
