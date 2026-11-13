"""Identity for OpsLedger (T009, T010-A, T011 part A, T013, T014).

Ships the password-hash records, the offline user provisioning path, the
opaque session domain module (creation, constant-time verify, expiry,
revocation), the CSRF domain module (short-lived opaque CSRF contexts
issued before login, rotation with the authenticated session, constant-time
verify, supersession, and the pure same-origin predicate), the explicit
operation permission checks (known application roles, base permissions per
role, the explicit purchase-approver grant path, and self-approval
prohibition), and the site membership module (users granted access to
specific sites within their organization, per-grant revocation, and
immediate deactivation). The csrf-contexts storage migration, HTTP guards,
and the login flow are later tasks (T011-B, T015).
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
from .permissions import (
    BASE_PERMISSIONS,
    KNOWN_ROLES,
    PURCHASE_APPROVE_PERMISSION,
    assert_not_self_approval,
    effective_permissions,
    has_permission,
    require_permission,
    require_role,
)
from .sites import (
    SiteGrant,
    active_site_ids,
    deactivate_membership,
    revoke_site_grant,
    require_site_access,
    has_site_access,
    site_access_active,
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
    "BASE_PERMISSIONS",
    "KNOWN_ROLES",
    "PURCHASE_APPROVE_PERMISSION",
    "assert_not_self_approval",
    "effective_permissions",
    "has_permission",
    "require_permission",
    "require_role",
    "SiteGrant",
    "site_access_active",
    "require_site_access",
    "has_site_access",
    "deactivate_membership",
    "revoke_site_grant",
    "active_site_ids",
]

