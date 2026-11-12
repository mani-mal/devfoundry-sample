"""CSRF context domain module: issue, verify, supersede, rotation (T011 part A).

CSRF contexts are short-lived opaque random tokens issued before login and
rotated with the authenticated session; only SHA-256 token hashes are ever
retained (:class:`CsrfContext`). The raw token is returned once by
:func:`issue_context` and is never a record field, never stored, and never
logged. Verification hashes the presented token the same way and compares in
constant time (:func:`hmac.compare_digest`).

The CSRF context lifecycle is the only business logic here: TTL-bounded
expiry (:data:`CSRF_TTL_SECONDS` by default, hard-capped at
:data:`MAX_CSRF_TTL_SECONDS`), supersession, and rotation, plus the pure
same-origin predicate (:func:`origin_allowed`). The csrf-contexts table
storage migration, HTTP guards, and the login flow are later tasks
(T011-B, T015).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from urllib.parse import SplitResult, urlsplit

from opsledger.core.clock import Clock, RealClock, require_aware_utc
from opsledger.core.errors import ValidationError

__all__ = [
    "CSRF_TTL_SECONDS",
    "MAX_CSRF_TTL_SECONDS",
    "CSRF_HEADER_NAME",
    "CsrfContext",
    "issue_context",
    "verify_csrf",
    "supersede",
    "rotate_context",
    "origin_allowed",
    "to_row",
    "from_row",
]

CSRF_TTL_SECONDS = 15 * 60
MAX_CSRF_TTL_SECONDS = 60 * 60
CSRF_HEADER_NAME = "X-CSRF-Token"

_TOKEN_HASH_LENGTH = 64
_HEX_DIGITS = frozenset("0123456789abcdef")

_DEFAULT_PORTS = {"http": 80, "https": 443}


@dataclass(frozen=True)
class CsrfContext:
    """One CSRF context: token hash and lifecycle fields, never the token."""

    token_hash: str
    created_at: datetime
    expires_at: datetime
    rotated_at: datetime | None = None


def _require_str(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be a string")
    return value


def _require_datetime(value: object, label: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValidationError(f"{label} must be a datetime")
    return value


def _validate_token_hash(value: str) -> None:
    if len(value) != _TOKEN_HASH_LENGTH or not set(value) <= _HEX_DIGITS:
        raise ValidationError(
            f"token_hash must be {_TOKEN_HASH_LENGTH} lowercase hex characters"
        )


def _require_row_key(row: dict[str, object], key: str) -> object:
    if key not in row:
        raise ValidationError(f"csrf context row must include '{key}'")
    return row[key]


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _effective_port(parts: SplitResult, fallback_scheme: str | None) -> int | None:
    explicit = parts.port
    if explicit is not None:
        return explicit
    scheme = parts.scheme or fallback_scheme
    if scheme in _DEFAULT_PORTS:
        return _DEFAULT_PORTS[scheme]
    return None


def issue_context(
    *,
    clock: Clock,
    ttl_seconds: int = CSRF_TTL_SECONDS,
    rng: Callable[[], bytes] | None = None,
) -> tuple[str, CsrfContext]:
    """Issue one short-lived CSRF context; the raw token is returned once.

    The token is 32 url-safe random bytes (``secrets.token_urlsafe(32)``);
    an injected ``rng`` keyword replaces the call for deterministic tests
    and must return bytes. ``ttl_seconds`` is validated against
    ``[1, MAX_CSRF_TTL_SECONDS]``. ``created_at``/``expires_at`` come
    from the injected clock and are timezone-aware UTC.
    """
    if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool):
        raise ValidationError("ttl_seconds must be an integer")
    if ttl_seconds < 1 or ttl_seconds > MAX_CSRF_TTL_SECONDS:
        raise ValidationError(
            f"ttl_seconds must be between 1 and {MAX_CSRF_TTL_SECONDS}"
        )
    if rng is not None:
        token_bytes = rng()
        if not isinstance(token_bytes, (bytes, bytearray)):
            raise ValidationError("rng must return bytes")
        raw_token = bytes(token_bytes).hex()
    else:
        raw_token = secrets.token_urlsafe(32)
    created_at = require_aware_utc(clock.now())
    context = CsrfContext(
        token_hash=_hash_token(raw_token),
        created_at=created_at,
        expires_at=created_at + timedelta(seconds=ttl_seconds),
    )
    return raw_token, context


def verify_csrf(raw_token: object, context: CsrfContext, *, clock: Clock) -> bool:
    """Verify a presented token against a context.

    Constant-time comparison via :func:`hmac.compare_digest`. Returns
    ``False`` on a hash mismatch, when the context has expired
    (``clock.now() >= context.expires_at``), or when it has been rotated
    away (``context.rotated_at is not None``). Raises :class:`ValidationError`
    for a non-str token or a malformed context.
    """
    if not isinstance(context, CsrfContext):
        raise ValidationError("context must be a CsrfContext")
    token_hash = _require_str(context.token_hash, "token_hash")
    _validate_token_hash(token_hash)
    require_aware_utc(_require_datetime(context.created_at, "created_at"))
    require_aware_utc(_require_datetime(context.expires_at, "expires_at"))
    presented_hash = _hash_token(_require_str(raw_token, "raw_token"))
    if not hmac.compare_digest(presented_hash, token_hash):
        return False
    if context.rotated_at is not None:
        return False
    if clock.now() >= context.expires_at:
        return False
    return True


def supersede(context: CsrfContext, *, clock: Clock) -> CsrfContext:
    """Return a copy with ``rotated_at`` set to the clock's instant.

    Idempotent: an already-rotated context is returned unchanged
    (the original ``rotated_at`` is kept).
    """
    if not isinstance(context, CsrfContext):
        raise ValidationError("context must be a CsrfContext")
    if context.rotated_at is not None:
        return context
    return replace(context, rotated_at=require_aware_utc(clock.now()))


def rotate_context(
    previous: CsrfContext,
    *,
    clock: Clock,
    ttl_seconds: int = CSRF_TTL_SECONDS,
    rng: Callable[[], bytes] | None = None,
) -> tuple[str, CsrfContext]:
    """Rotate the CSRF context issued with an authenticated session.

    Validates the previous context first: it must not be expired
    (``clock.now() < previous.expires_at``) and must not already be rotated
    (``previous.rotated_at is None``). Then issues a fresh context with the
    same TTL rules as :func:`issue_context`. Rotation invalidates the
    previous raw token once the caller supersedes the previous context
    (via :func:`supersede`).
    """
    if not isinstance(previous, CsrfContext):
        raise ValidationError("previous must be a CsrfContext")
    _validate_token_hash(_require_str(previous.token_hash, "token_hash"))
    require_aware_utc(_require_datetime(previous.created_at, "created_at"))
    require_aware_utc(_require_datetime(previous.expires_at, "expires_at"))
    if clock.now() >= previous.expires_at:
        raise ValidationError("previous context has expired")
    if previous.rotated_at is not None:
        raise ValidationError("previous context has already been rotated")
    return issue_context(clock=clock, ttl_seconds=ttl_seconds, rng=rng)


def origin_allowed(origin: object, expected_host: str) -> bool:
    """Return whether a request's ``Origin`` is same-origin with the server.

    Pure predicate; never raises. ``expected_host`` is a Host-header value
    like ``"127.0.0.1:8080"`` (scheme-less); it must include the port when
    the server runs on a non-default port.

    Hostnames are compared case-insensitively, and effective ports are
    compared: a port is the explicit one, else 80 for http, 443 for https,
    else None; None matches only None. The effective port for the expected
    host falls back to the default port of the request's scheme.
    """
    if not isinstance(origin, str) or not origin:
        return False
    try:
        origin_parts = urlsplit(origin)
        if origin_parts.scheme not in ("http", "https"):
            return False
        origin_hostname = origin_parts.hostname
        if not origin_hostname:
            return False
        host_parts = urlsplit("//" + expected_host)
        expected_hostname = host_parts.hostname
        if not expected_hostname:
            return False
    except ValueError:
        return False
    if origin_hostname.casefold() != expected_hostname.casefold():
        return False
    origin_port = _effective_port(origin_parts, None)
    expected_port = _effective_port(host_parts, origin_parts.scheme)
    if origin_port != expected_port:
        return False
    return True


def to_row(context: CsrfContext) -> dict[str, object]:
    """Map a context to the csrf-contexts-table row shape (token hash on)."""
    return {
        "token_hash": context.token_hash,
        "created_at": context.created_at,
        "expires_at": context.expires_at,
        "rotated_at": context.rotated_at,
    }


def from_row(row: dict[str, object]) -> CsrfContext:
    """Map a csrf-contexts-table row back to a context; malformed rows are rejected."""
    token_hash = _require_str(_require_row_key(row, "token_hash"), "token_hash")
    _validate_token_hash(token_hash)
    created_at = require_aware_utc(
        _require_datetime(_require_row_key(row, "created_at"), "created_at")
    )
    expires_at = require_aware_utc(
        _require_datetime(_require_row_key(row, "expires_at"), "expires_at")
    )
    rotated_at_raw = _require_row_key(row, "rotated_at")
    rotated_at = (
        require_aware_utc(_require_datetime(rotated_at_raw, "rotated_at"))
        if rotated_at_raw is not None
        else None
    )
    return CsrfContext(
        token_hash=token_hash,
        created_at=created_at,
        expires_at=expires_at,
        rotated_at=rotated_at,
    )
