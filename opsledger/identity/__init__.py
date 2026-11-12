"""Identity for OpsLedger (T009, T010-A).

Ships the password-hash records, the offline user provisioning path, and the
opaque session domain module (creation, constant-time verify, expiry,
revocation). The sessions storage migration, login, cookies, and HTTP
endpoints are later tasks (T010-B, T011, T015).
"""

from .passwords import (
    PROTOCOL_VERSION,
    PasswordHash,
    SCRYPT_N,
    SCRYPT_P,
    SCRYPT_R,
    ScryptParams,
    from_row,
    hash_password,
    provision_user,
    provision_user_sql,
    scrypt_unavailable,
    to_row,
    verify_password,
)
from .sessions import (
    MAX_SESSION_TTL_SECONDS,
    SESSION_TTL_SECONDS,
    SessionRecord,
    create_session,
    from_row as from_session_row,
    revoke_session,
    to_row as to_session_row,
    verify_session,
)

__all__ = [
    "from_row",
    "from_session_row",
    "hash_password",
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
    "to_session_row",
    "verify_password",
    "MAX_SESSION_TTL_SECONDS",
    "SESSION_TTL_SECONDS",
    "SessionRecord",
    "create_session",
    "verify_session",
    "revoke_session",
]
