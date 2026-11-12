"""Password-hash records and offline user provisioning (T009, spec §8.3).

The raw password is never stored: only scrypt-derived hash records are. Each
record pins the scrypt work factors used, a per-password random salt, and
the protocol version, so a stored hash can always be recomputed exactly and
a future change of parameters is explicit.

Verification recomputes the derived key with the record's own params and
salt and compares in constant time (:func:`hmac.compare_digest`). Malformed
or unknown-version records are rejected with :class:`ValidationError`
instead of raising raw exceptions or comparing garbage.

Provisioning is the only business transaction here: it inserts the user row
with the hash columns inside :func:`opsledger.core.db.transaction`. Sessions,
login, and HTTP endpoints are later tasks (T010, T011, T015). The raw
password is never stored, logged, or returned.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, replace

from opsledger.core.clock import Clock, RealClock, format_rfc3339
from opsledger.core.db import transaction
from opsledger.core.errors import ValidationError

__all__ = [
    "hash_password",
    "from_row",
    "provision_user",
    "provision_user_sql",
    "PROTOCOL_VERSION",
    "scrypt_unavailable",
    "SCRYPT_N",
    "SCRYPT_P",
    "SCRYPT_R",
    "PasswordHash",
    "ScryptParams",
    "to_row",
    "verify_password",
]

PROTOCOL_VERSION = 1

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1

provision_user_sql = (
    "INSERT INTO users (id, email, display_name, created_at,"
    " salt, hash, n, r, p, protocol_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_SALT_BYTES = 16
_DERIVED_KEY_BYTES = 64
_HEX_DIGITS = frozenset("0123456789abcdef")


@dataclass(frozen=True)
class ScryptParams:
    """Pinned scrypt work factors recorded with every hash record."""

    n: int = SCRYPT_N
    r: int = SCRYPT_R
    p: int = SCRYPT_P

    def validate(self) -> None:
        """Reject work factors outside the allowed domain."""
        if self.n <= 1 or (self.n & (self.n - 1)) != 0:
            raise ValidationError(
                "scrypt parameter n must be a power of two greater than 1"
            )
        if self.r < 1:
            raise ValidationError("scrypt parameter r must be at least 1")
        if self.p < 1:
            raise ValidationError("scrypt parameter p must be at least 1")


@dataclass(frozen=True)
class PasswordHash:
    """One password-hash record: derived values only, never the password."""

    user_id: str
    salt: str
    hash: str
    params: ScryptParams
    protocol_version: int
    created_at: str


def _require_str(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be a string")
    return value


def _require_non_empty(value: str, label: str) -> str:
    if not value:
        raise ValidationError(f"{label} must not be empty")
    return value


def _normalize_email(email: str) -> str:
    """Normalize to trimmed lowercase and validate the local@domain shape."""
    normalized = email.strip().lower()
    if normalized.count("@") != 1:
        raise ValidationError("email must be a local@domain address")
    local, _, domain = normalized.partition("@")
    if not local or not domain:
        raise ValidationError("email must be a local@domain address")
    return normalized


def _validate_hex_field(value: str, expected_length: int, label: str) -> None:
    if len(value) != expected_length or not set(value) <= _HEX_DIGITS:
        raise ValidationError(
            f"{label} must be {expected_length} lowercase hex characters"
        )


def _derive_key(password: str, salt_hex: str, params: ScryptParams) -> bytes:
    """Derive the 64-byte scrypt key; translate ValueError to public errors."""
    try:
        return hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=params.n,
            r=params.r,
            p=params.p,
            dklen=_DERIVED_KEY_BYTES,
        )
    except ValueError as error:
        raise ValidationError(
            "scrypt is unavailable in this OpenSSL build; password hashing"
            " cannot proceed"
        ) from error


def hash_password(
    password: str,
    *,
    params: ScryptParams | None = None,
    clock: Clock | None = None,
    rng: Callable[[int], bytes] | None = None,
) -> PasswordHash:
    """Derive one password-hash record; the raw password is not retained.

    The salt is 16 random bytes (injected ``rng`` for deterministic tests).
    The derived key is 64 bytes; both are stored as lowercase hex.
    ``created_at`` is canonical RFC3339 ``Z`` text through the injected
    clock (real wall clock by default). ``params`` defaults to
    :class:`ScryptParams` with the shipped work factors.
    """
    params = params if params is not None else ScryptParams()
    params.validate()
    password = _require_non_empty(_require_str(password, "password"), "password")
    if rng is not None:
        salt = rng(_SALT_BYTES)
        if not isinstance(salt, (bytes, bytearray)):
            raise ValidationError("rng must return bytes")
        salt_hex = bytes(salt).hex()
    else:
        salt_hex = secrets.token_bytes(_SALT_BYTES).hex()
    derived = _derive_key(password, salt_hex, params)
    clock = clock if clock is not None else RealClock()
    return PasswordHash(
        user_id="",
        salt=salt_hex,
        hash=derived.hex(),
        params=params,
        protocol_version=PROTOCOL_VERSION,
        created_at=format_rfc3339(clock.now()),
    )


def verify_password(password: str, record: PasswordHash) -> bool:
    """Recompute the derived key with the record's own params and salt.

    Constant-time comparison via :func:`hmac.compare_digest`. Returns
    ``False`` for a wrong password; raises :class:`ValidationError` for an
    unknown protocol version or malformed hex fields.
    """
    if not isinstance(record, PasswordHash):
        raise ValidationError("record must be a PasswordHash")
    if record.protocol_version != PROTOCOL_VERSION:
        raise ValidationError("password record has an unknown protocol version")
    if not isinstance(record.params, ScryptParams):
        raise ValidationError("password record params are malformed")
    record.params.validate()
    password = _require_str(password, "password")
    salt_hex = _require_str(record.salt, "salt")
    derived_hex = _require_str(record.hash, "hash")
    _validate_hex_field(salt_hex, _SALT_BYTES * 2, "salt")
    _validate_hex_field(derived_hex, _DERIVED_KEY_BYTES * 2, "hash")
    derived = _derive_key(password, salt_hex, record.params)
    return hmac.compare_digest(derived, bytes.fromhex(derived_hex))


def to_row(record: PasswordHash) -> dict[str, object]:
    """Map a record to the users-provisioning row shape (hash columns on).

    Identity columns (``email``, ``display_name``) are blank: the record
    carries only derived values. Callers fill them before the write.
    """
    return {
        "id": record.user_id,
        "email": "",
        "display_name": "",
        "created_at": record.created_at,
        "salt": record.salt,
        "hash": record.hash,
        "n": record.params.n,
        "r": record.params.r,
        "p": record.params.p,
        "protocol_version": record.protocol_version,
    }


def from_row(row: dict[str, object]) -> PasswordHash:
    """Map a provisioning row back to a record (hash columns on)."""
    return PasswordHash(
        user_id=_require_str(row["id"], "id"),
        salt=_require_str(row["salt"], "salt"),
        hash=_require_str(row["hash"], "hash"),
        params=ScryptParams(n=int(row["n"]), r=int(row["r"]), p=int(row["p"])),
        protocol_version=int(row["protocol_version"]),
        created_at=_require_str(row["created_at"], "created_at"),
    )


def provision_user(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    email: str,
    display_name: str,
    password: str,
    clock: Clock | None = None,
    rng: Callable[[int], bytes] | None = None,
) -> PasswordHash:
    """Insert the user row with the hash columns in one explicit transaction.

    The email is normalized (trimmed, lowercase) before validation and the
    write. A duplicate email surfaces ``sqlite3.IntegrityError`` as
    :class:`ValidationError`; nothing is stored when the insert fails. With
    scrypt unavailable the preflight raises before any write.
    """
    user_id = _require_non_empty(_require_str(user_id, "user_id"), "user_id")
    email = _require_str(email, "email")
    normalized_email = _normalize_email(email)
    display_name = _require_non_empty(
        _require_str(display_name, "display_name"), "display_name"
    )
    if scrypt_unavailable():
        raise ValidationError(
            "scrypt is unavailable in this OpenSSL build; user provisioning"
            " cannot proceed"
        )
    record = hash_password(password, clock=clock, rng=rng)
    try:
        with transaction(conn) as tx:
            tx.execute(
                provision_user_sql,
                (
                    user_id,
                    normalized_email,
                    display_name,
                    record.created_at,
                    record.salt,
                    record.hash,
                    record.params.n,
                    record.params.r,
                    record.params.p,
                    record.protocol_version,
                ),
            )
    except sqlite3.IntegrityError as error:
        raise ValidationError(
            "user could not be provisioned; identity conflicts with existing"
            " state or schema"
        ) from error
    return replace(record, user_id=user_id)


def scrypt_unavailable() -> bool:
    """True when hashlib.scrypt raises ValueError (OpenSSL without scrypt)."""
    try:
        hashlib.scrypt(
            b"opencode-preflight", salt=b"opencode", n=2, r=8, p=1, dklen=1
        )
    except ValueError:
        return True
    return False
