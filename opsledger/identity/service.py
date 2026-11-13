"""Identity domain service: login, logout, session resolution (T011-D).

Identity transaction boundary (spec §8.2/§8.3). Login verifies the
presented password against the stored scrypt hash and provisions one
TTL-bounded session; logout revokes the session owned by a presented raw
token; :func:`resolve_session` turns a presented raw token into the joined
session/session row for downstream authorization.

Credential isolation: every credential failure raises the single module
constant :data:`LOGIN_FAILURE_MESSAGE` and never reveals which factor
(email or password) failed. Tokens are opaque: only SHA-256 token hashes
are stored; the raw token is returned once by :func:`login` and is never
logged, stored, or embedded in records.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from typing import Any

from opsledger.core.clock import Clock, RealClock, require_aware_utc
from opsledger.core.db import transaction
from opsledger.core.errors import PermissionDeniedError, ValidationError
from opsledger.identity.passwords import (
    ScryptParams,
    from_row as password_from_row,
    verify_password,
)
from opsledger.identity.sessions import (
    SessionRecord,
    create_session,
    from_row as session_from_row,
    revoke_session,
    verify_session,
)

__all__ = ["LOGIN_FAILURE_MESSAGE", "login", "logout", "resolve_session"]

LOGIN_FAILURE_MESSAGE = "invalid email or password"

_SELECT_USER_BY_EMAIL_SQL = (
    "SELECT id, email, display_name, created_at,"
    " salt, hash, n, r, p, protocol_version"
    " FROM users WHERE email = ?"
)

_INSERT_SESSION_SQL = (
    "INSERT INTO sessions (token_hash, user_id, created_at, expires_at, revoked_at)"
    " VALUES (?, ?, ?, ?, NULL)"
)

_SELECT_SESSION_BY_TOKEN_HASH_SQL = (
    "SELECT token_hash, user_id, created_at, expires_at, revoked_at"
    " FROM sessions WHERE token_hash = ?"
)

_SELECT_SESSION_JOINED_SQL = (
    "SELECT s.token_hash, s.user_id, s.created_at, s.expires_at, s.revoked_at,"
    " u.email AS email, u.display_name AS display_name"
    " FROM sessions s JOIN users u ON u.id = s.user_id"
    " WHERE s.token_hash = ?"
)

_UPDATE_SESSION_REVOKED_SQL = "UPDATE sessions SET revoked_at = ? WHERE token_hash = ?"


def _normalize_email(email: str) -> str:
    """Trim and lowercase the presented email."""
    return email.strip().lower()


def _hash_token(raw_token: str) -> str:
    """SHA-256 hexdigest of the utf-8 token; same retention shape as sessions."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _text_from_instant(instant: datetime) -> str:
    """Canonical RFC3339 Z text: UTC, second precision."""
    canonical = instant.astimezone(timezone.utc).replace(microsecond=0)
    return canonical.strftime("%Y-%m-%dT%H:%M:%SZ")


def _instant_from_text(text: str) -> datetime:
    """Parse canonical RFC3339 Z text into aware UTC."""
    try:
        instant = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise ValidationError("invalid stored timestamp") from error
    return instant.replace(tzinfo=timezone.utc)


def _session_record_from_row(row: sqlite3.Row) -> SessionRecord:
    """Rebuild the record from a sessions-table row; malformed rows rejected."""
    return session_from_row(
        {
            "token_hash": str(row["token_hash"]),
            "user_id": str(row["user_id"]),
            "created_at": _instant_from_text(str(row["created_at"])),
            "expires_at": _instant_from_text(str(row["expires_at"])),
            "revoked_at": (
                _instant_from_text(str(row["revoked_at"]))
                if row["revoked_at"] is not None
                else None
            ),
        }
    )


def login(
    conn: sqlite3.Connection,
    *,
    email: str,
    password: str,
    clock: Clock,
) -> tuple[str, Any, str]:
    """Verify the presented credentials and provision one session.

    The email is normalized locally (trimmed, lowercase) and the user row is
    looked up by normalized email. A missing user or a scrypt mismatch
    surfaces :class:`PermissionDeniedError` with :data:`LOGIN_FAILURE_MESSAGE`
    and never reveals which factor failed. On success one session row is
    inserted inside one explicit transaction; the raw token is returned only
    here and is never logged, stored, or persisted.
    """
    normalized_email = _normalize_email(email)
    user_row = conn.execute(
        _SELECT_USER_BY_EMAIL_SQL, (normalized_email,)
    ).fetchone()
    if user_row is None:
        raise PermissionDeniedError(LOGIN_FAILURE_MESSAGE)
    password_record = password_from_row(
        {
            **dict(user_row),
            "params": ScryptParams(n=user_row["n"], r=user_row["r"], p=user_row["p"]),
        }
    )
    if not verify_password(password, password_record):
        raise PermissionDeniedError(LOGIN_FAILURE_MESSAGE)
    user_id = str(user_row["id"])
    raw_token, session_record = create_session(user_id, clock=clock)
    with transaction(conn) as tx:
        tx.execute(
            _INSERT_SESSION_SQL,
            (
                session_record.token_hash,
                session_record.user_id,
                _text_from_instant(session_record.created_at),
                _text_from_instant(session_record.expires_at),
            ),
        )
    return raw_token, session_record, user_id


def logout(
    conn: sqlite3.Connection,
    *,
    raw_token: str,
    clock: Clock,
) -> None:
    """Revoke the session owned by the presented token; silent no-op otherwise.

    Unknown tokens and already-revoked tokens are silent no-ops and never
    raise. When a live session is found, its revocation instant is computed
    once via :func:`revoke_session` and written in one explicit transaction.
    """
    token_hash = _hash_token(raw_token)
    session_row = conn.execute(
        _SELECT_SESSION_BY_TOKEN_HASH_SQL, (token_hash,)
    ).fetchone()
    if session_row is None or session_row["revoked_at"] is not None:
        return
    record = _session_record_from_row(session_row)
    revoked_record = revoke_session(record, clock=clock)
    revoked_instant = revoked_record.revoked_at
    if revoked_instant is None:
        return
    with transaction(conn) as tx:
        tx.execute(
            _UPDATE_SESSION_REVOKED_SQL, (_text_from_instant(revoked_instant), token_hash)
        )


def resolve_session(
    conn: sqlite3.Connection,
    *,
    raw_token: str,
    clock: Clock,
) -> sqlite3.Row | None:
    """Resolve a presented raw token into the joined session row, or None.

    Returns the joined session/session row only when the presented token
    matches a live session: hash matches, ``clock.now() < expires_at``, and
    ``revoked_at IS NULL``. Every other case — missing session, expired
    session, revoked session, malformed stored lifecycle fields — returns
    None and never raises.
    """
    presented_hash = _hash_token(raw_token)
    session_row = conn.execute(
        _SELECT_SESSION_JOINED_SQL, (presented_hash,)
    ).fetchone()
    if session_row is None:
        return None
    try:
        record = _session_record_from_row(session_row)
        if not verify_session(raw_token, record, clock=clock):
            return None
    except ValidationError:
        return None
    return session_row
