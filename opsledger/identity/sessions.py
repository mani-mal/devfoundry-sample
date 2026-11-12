"""Opaque session domain module: creation, verify, revocation (T010-A).

Sessions are opaque random tokens; only SHA-256 token hashes are ever
retained (:class:`SessionRecord`). The raw token is returned once by
:func:`create_session` and is never a record field, never stored, and never
logged. Verification hashes the presented token the same way and compares in
constant time (:func:`hmac.compare_digest`).

Session lifecycle is the only business logic here: TTL-bounded expiry
(:data:`SESSION_TTL_SECONDS` by default, hard-capped at
:data:`MAX_SESSION_TTL_SECONDS`) and revocation. Database storage migration,
login, cookies, and HTTP endpoints are later tasks (T011, T015).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from opsledger.core.clock import Clock, RealClock, require_aware_utc
from opsledger.core.errors import ValidationError

__all__ = [
    "SESSION_TTL_SECONDS",
    "MAX_SESSION_TTL_SECONDS",
    "SessionRecord",
    "create_session",
    "verify_session",
    "revoke_session",
    "to_row",
    "from_row",
]

SESSION_TTL_SECONDS = 8 * 60 * 60
MAX_SESSION_TTL_SECONDS = 30 * 24 * 60 * 60

_TOKEN_HASH_LENGTH = 64
_HEX_DIGITS = frozenset("0123456789abcdef")


@dataclass(frozen=True)
class SessionRecord:
    """One session record: token hash and lifecycle fields, never the token."""

    token_hash: str
    user_id: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None


def _require_str(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be a string")
    return value


def _require_non_empty(value: str, label: str) -> str:
    if not value:
        raise ValidationError(f"{label} must not be empty")
    return value


def _validate_token_hash(value: str) -> None:
    if len(value) != _TOKEN_HASH_LENGTH or not set(value) <= _HEX_DIGITS:
        raise ValidationError(
            f"token_hash must be {_TOKEN_HASH_LENGTH} lowercase hex characters"
        )


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_session(
    user_id: str,
    *,
    clock: Clock,
    ttl_seconds: int = SESSION_TTL_SECONDS,
    rng: Callable[[], bytes] | None = None,
) -> tuple[str, SessionRecord]:
    """Create one session; the raw token is returned once and not retained.

    The token is 32 url-safe random bytes (``secrets.token_urlsafe(32)``);
    an injected ``rng`` keyword replaces the call for deterministic tests
    and must return bytes. ``ttl_seconds`` is validated against
    ``[1, MAX_SESSION_TTL_SECONDS]``. ``created_at``/``expires_at`` come
    from the injected clock and are timezone-aware UTC.
    """
    user_id = _require_non_empty(_require_str(user_id, "user_id"), "user_id")
    if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool):
        raise ValidationError("ttl_seconds must be an integer")
    if ttl_seconds < 1 or ttl_seconds > MAX_SESSION_TTL_SECONDS:
        raise ValidationError(
            f"ttl_seconds must be between 1 and {MAX_SESSION_TTL_SECONDS}"
        )
    if rng is not None:
        token_bytes = rng()
        if not isinstance(token_bytes, (bytes, bytearray)):
            raise ValidationError("rng must return bytes")
        raw_token = bytes(token_bytes).hex()
    else:
        raw_token = secrets.token_urlsafe(32)
    created_at = require_aware_utc(clock.now())
    record = SessionRecord(
        token_hash=_hash_token(raw_token),
        user_id=user_id,
        created_at=created_at,
        expires_at=created_at + timedelta(seconds=ttl_seconds),
    )
    return raw_token, record


def verify_session(raw_token: object, record: SessionRecord, *, clock: Clock) -> bool:
    """Verify a presented token against a record.

    Constant-time comparison via :func:`hmac.compare_digest`. Returns
    ``False`` on a hash mismatch, when the session has expired
    (``clock.now() >= record.expires_at``), or when it has been revoked
    (``record.revoked_at is not None``). Raises :class:`ValidationError`
    for a non-str token or a malformed record.
    """
    if not isinstance(record, SessionRecord):
        raise ValidationError("record must be a SessionRecord")
    token_hash = _require_str(record.token_hash, "token_hash")
    _validate_token_hash(token_hash)
    _require_non_empty(_require_str(record.user_id, "user_id"), "user_id")
    require_aware_utc(_require_datetime(record.created_at, "created_at"))
    require_aware_utc(_require_datetime(record.expires_at, "expires_at"))
    presented_hash = _hash_token(_require_str(raw_token, "raw_token"))
    if not hmac.compare_digest(presented_hash, token_hash):
        return False
    if record.revoked_at is not None:
        return False
    if clock.now() >= record.expires_at:
        return False
    return True


def _require_datetime(value: object, label: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValidationError(f"{label} must be a datetime")
    return value


def revoke_session(record: SessionRecord, *, clock: Clock) -> SessionRecord:
    """Return a copy with ``revoked_at`` set to the clock's instant.

    Idempotent: an already-revoked record is returned unchanged.
    """
    if not isinstance(record, SessionRecord):
        raise ValidationError("record must be a SessionRecord")
    if record.revoked_at is not None:
        return record
    return replace(record, revoked_at=require_aware_utc(clock.now()))


def to_row(record: SessionRecord) -> dict[str, object]:
    """Map a record to the sessions-table row shape (token hash on)."""
    return {
        "token_hash": record.token_hash,
        "user_id": record.user_id,
        "created_at": record.created_at,
        "expires_at": record.expires_at,
        "revoked_at": record.revoked_at,
    }


def from_row(row: dict[str, object]) -> SessionRecord:
    """Map a sessions-table row back to a record; malformed rows are rejected."""
    token_hash = _require_str(row["token_hash"], "token_hash")
    _validate_token_hash(token_hash)
    user_id = _require_str(row["user_id"], "user_id")
    created_at = require_aware_utc(_require_datetime(row["created_at"], "created_at"))
    expires_at = require_aware_utc(_require_datetime(row["expires_at"], "expires_at"))
    revoked_at_raw = row["revoked_at"]
    revoked_at = (
        require_aware_utc(_require_datetime(revoked_at_raw, "revoked_at"))
        if revoked_at_raw is not None
        else None
    )
    return SessionRecord(
        token_hash=token_hash,
        user_id=user_id,
        created_at=created_at,
        expires_at=expires_at,
        revoked_at=revoked_at,
    )
