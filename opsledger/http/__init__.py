"""HTTP adapter for OpsLedger: routing, JSON error envelope, static allowlist.

Handlers are thin adapters (routing, bounded input, error mapping); business
transactions live in domain services. This package provides the router over
:mod:`http.server`, the canonical error envelope, and the static file
allowlist (serving only allowlisted files below ``web/``, refusing traversal
and symlinks); the HTTP server wiring for static files is a later task.
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
from .static import (
    DEFAULT_ALLOWED_TYPES,
    StaticFile,
    read_static,
    resolve_static,
)

__all__ = [
    "DEFAULT_BODY_LIMIT_BYTES",
    "DEFAULT_HOST",
    "DEFAULT_ALLOWED_TYPES",
    "INTERNAL_ERROR_CODE",
    "INTERNAL_ERROR_MESSAGE",
    "StaticFile",
    "InputError",
    "Request",
    "Router",
    "RouterError",
    "RouterServer",
    "read_static",
    "build_error_body",
    "error_response_for",
    "http_status_for_error",
    "new_request_id",
    "resolve_static",
]
