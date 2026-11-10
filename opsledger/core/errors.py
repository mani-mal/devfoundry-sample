"""Application error types shared across OpsLedger services.

Errors are safe to surface to callers: they carry a stable machine-readable
code, a public message, and optional safe field details. Messages never
contain tracebacks or internal details (paths, SQL, stack frames).
"""

from __future__ import annotations

__all__ = [
    "ApplicationError",
    "ConflictError",
    "NotFoundError",
    "PermissionDeniedError",
    "ValidationError",
]


class ApplicationError(Exception):
    """Base class for OpsLedger application errors.

    Attributes:
        code: Stable machine-readable error code. Each subclass documents
            a default code; callers may override it explicitly.
        message: Public message safe to show to callers.
        fields: Optional safe field details (field name -> public reason).
            Never includes internal values or tracebacks.
    """

    default_code: str = "application_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        fields: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code if code is not None else self.default_code
        self.fields: dict[str, str] = dict(fields) if fields else {}

    def to_payload(self) -> dict[str, object]:
        """Return the public error payload for HTTP/JSON error envelopes."""
        payload: dict[str, object] = {"code": self.code, "message": str(self)}
        if self.fields:
            payload["fields"] = dict(self.fields)
        return payload


class ValidationError(ApplicationError):
    """Caller input failed validation. Default code: ``validation_error``."""

    default_code = "validation_error"


class NotFoundError(ApplicationError):
    """Requested record does not exist in scope. Default code: ``not_found``."""

    default_code = "not_found"


class PermissionDeniedError(ApplicationError):
    """Caller lacks required membership or role. Default code: ``permission_denied``."""

    default_code = "permission_denied"


class ConflictError(ApplicationError):
    """Request conflicts with current state. Default code: ``conflict``."""

    default_code = "conflict"
