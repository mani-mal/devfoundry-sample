"""Identity for OpsLedger (T009).

Ships the password-hash records and the offline user provisioning path.
Sessions, login, HTTP endpoints, and UI are later tasks (T010, T011, T015).
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

__all__ = [
    "from_row",
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
    "verify_password",
]
