"""Core foundation for OpsLedger services (T001, T002, T012).

Ships the shared application error types, the UTC clocks, the SQLite
connection factory and transaction context, and the organization identity
context with no-leak scoped lookups used by every later business module.
"""

from .clock import (
    Clock,
    FixedClock,
    RFC3339_Z_FORMAT,
    RealClock,
    format_rfc3339,
    require_aware_utc,
)
from .context import (
    OrganizationContext,
    require_context,
    require_owned,
    scoped_all,
    scoped_first,
)
from .errors import (
    ApplicationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from .db import connect, transaction
from .idempotency import (
    IDEMPOTENCY_DIGEST_CONFLICT_MESSAGE,
    IDEMPOTENCY_NOT_PENDING_MESSAGE,
    begin_idempotency,
    canonical_request_digest,
    complete_idempotency,
    fail_idempotency,
    get_idempotency_record,
)

__all__ = [
    "ApplicationError",
    "Clock",
    "OrganizationContext",
    "require_context",
    "require_owned",
    "scoped_all",
    "scoped_first",
    "ConflictError",
    "connect",
    "FixedClock",
    "begin_idempotency",
    "canonical_request_digest",
    "complete_idempotency",
    "fail_idempotency",
    "get_idempotency_record",
    "IDEMPOTENCY_DIGEST_CONFLICT_MESSAGE",
    "IDEMPOTENCY_NOT_PENDING_MESSAGE",
    "NotFoundError",
    "PermissionDeniedError",
    "RFC3339_Z_FORMAT",
    "RealClock",
    "ValidationError",
    "transaction",
    "format_rfc3339",
    "require_aware_utc",
]
