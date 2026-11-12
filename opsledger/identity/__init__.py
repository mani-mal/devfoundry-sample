"""Identity for OpsLedger (T009, T010-A, T011 part A).

Ships the password-hash records, the offline user provisioning path, the
opaque session domain module (creation, constant-time verify, expiry,
revocation), and the CSRF domain module (short-lived opaque CSRF contexts
issued before login, rotation with the authenticated session, constant-time
verify, supersession, and the pure same-origin predicate). The csrf-contexts
storage migration, HTTP guards, and the login flow are later tasks
(T011-B, T015).
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
from .csrf import (
    CSRF_HEADER_NAME,
    CSRF_TTL_SECONDS,
    MAX_CSRF_TTL_SECONDS,
    CsrfContext,
    from_row as from_csrf_row,
    issue_context,
    origin_allowed,
    rotate_context,
    supersede,
    to_row as to_csrf_row,
    verify_csrf,
)

__all__ = [
    "from_row",
    "from_csrf_row",
    "from_session_row",
    "to_csrf_row",
    "to_session_row",
    "hash_password",
    "provision_user",
    "provision_user_sql",
    "PROTOCOL_VERSION",
    "verify_password",
    "scrypt_unavailable",
    "SCRYPT_N",
    "SCRYPT_P",
    "SCRYPT_R",
    "PasswordHash",
    "ScryptParams",
    "CSRF_HEADER_NAME",
    "CSRF_TTL_SECONDS",
    "MAX_CSRF_TTL_SECONDS",
    "CsrfContext",
    "issue_context",
    "origin_allowed",
    "rotate_context",
    "supersede",
    "verify_csrf",
]

