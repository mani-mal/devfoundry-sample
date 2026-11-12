"""Canonical JSON error envelope for the OpsLedger HTTP adapter.

Every error response body is exactly:

    {"error": {"code": "<stable code>", "message": "<public message>",
               "request_id": "<opaque id>"}}

Codes are stable and machine-readable; messages are public and never contain
tracebacks, exception text, or internal details. This module is the single
place that maps a raised error to an HTTP status and envelope body.
"""

from __future__ import annotations

import uuid

from opsledger.core.errors import (
    ApplicationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

__all__ = [
    "INTERNAL_ERROR_CODE",
    "INTERNAL_ERROR_MESSAGE",
    "InputError",
    "build_error_body",
    "error_response_for",
    "http_status_for_error",
    "new_request_id",
]

INTERNAL_ERROR_CODE = "internal_error"
INTERNAL_ERROR_MESSAGE = "internal server error"


class InputError(Exception):
    """Bounded-input violation detected while parsing one request.

    Raised during request parsing (for example malformed JSON or an
    unsupported content type). The transport adapter maps it to a canonical
    envelope with this HTTP status, stable code, and public message.
    """

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def new_request_id() -> str:
    """Return an opaque correlation identifier for one request."""
    return uuid.uuid4().hex


def build_error_body(code: str, message: str, request_id: str) -> dict[str, object]:
    """Return the canonical error envelope body (this shape, nothing more)."""
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        }
    }


_HTTP_STATUS_BY_ERROR_TYPE: tuple[tuple[type[ApplicationError], int], ...] = (
    (ConflictError, 409),
    (NotFoundError, 404),
    (PermissionDeniedError, 403),
    (ValidationError, 422),
)


def http_status_for_error(error: BaseException) -> int:
    """Map a raised error to its HTTP status; unknown errors get 500."""
    for error_type, status in _HTTP_STATUS_BY_ERROR_TYPE:
        if isinstance(error, error_type):
            return status
    return 500


def error_response_for(
    error: BaseException, request_id: str
) -> tuple[int, dict[str, object]]:
    """Map any raised error to (http status, canonical error envelope body).

    Application errors surface their stable code and public message;
    bounded-input violations surface their stable code and public message
    with the status detected at parse time; any other error is a generic
    internal failure with a constant message and no exception details.
    """
    if isinstance(error, InputError):
        return error.status, build_error_body(error.code, error.message, request_id)
    status = http_status_for_error(error)
    if isinstance(error, ApplicationError):
        return status, build_error_body(error.code, str(error), request_id)
    return 500, build_error_body(INTERNAL_ERROR_CODE, INTERNAL_ERROR_MESSAGE, request_id)
