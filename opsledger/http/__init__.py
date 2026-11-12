"""HTTP adapter for OpsLedger: routing and JSON error envelope.

Handlers are thin adapters (routing, bounded input, error mapping); business
transactions live in domain services. This package currently provides the
router over :mod:`http.server` and the canonical error envelope; later tasks
add authentication, readiness, and static file handling.
"""

from .envelope import (
    INTERNAL_ERROR_CODE,
    INTERNAL_ERROR_MESSAGE,
    InputError,
    build_error_body,
    error_response_for,
    http_status_for_error,
    new_request_id,
)
from .router import (
    DEFAULT_HOST,
    DEFAULT_BODY_LIMIT_BYTES,
    Request,
    Router,
    RouterError,
    RouterServer,
)

__all__ = [
    "DEFAULT_BODY_LIMIT_BYTES",
    "DEFAULT_HOST",
    "INTERNAL_ERROR_CODE",
    "INTERNAL_ERROR_MESSAGE",
    "InputError",
    "Request",
    "Router",
    "RouterError",
    "RouterServer",
    "build_error_body",
    "error_response_for",
    "http_status_for_error",
    "new_request_id",
]
