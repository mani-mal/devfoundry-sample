"""Idempotency record core for OpsLedger (T037, M5).

Scope per spec §7.3: organization + actor + operation + key. Every begin
stores a canonical request digest (sorted-key JSON, sha256 hex). The same
key with the same digest resolves the prior record (replay); the same key
with a different digest raises ConflictError (HTTP 409) and the original
effect is preserved. Concurrent repeats produce one business effect: the
UNIQUE (organization_id, actor_id, operation, key) constraint admits
exactly one row per scope, and every write runs in one IMMEDIATE
transaction so racing begins serialize -- the loser sees the winner's
committed row and replays it.

A command that succeeds completes its record with the JSON result payload
that replays return; a command that fails marks its record failed
(terminal -- a retry needs a NEW key). Lookup helpers carry the
authenticated organization context: missing and cross-organization
records surface the same NotFoundError, no existence leak.
"""

from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from opsledger.core.clock import Clock, format_rfc3339
from opsledger.core.context import require_context, require_owned
from opsledger.core.db import transaction
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError

__all__ = [
    "IDEMPOTENCY_DIGEST_CONFLICT_MESSAGE",
    "IDEMPOTENCY_NOT_PENDING_MESSAGE",
    "begin_idempotency",
    "canonical_request_digest",
    "complete_idempotency",
    "fail_idempotency",
    "get_idempotency_record",
]

IDEMPOTENCY_DIGEST_CONFLICT_MESSAGE = (
    "idempotency key already used with a different request payload"
)

IDEMPOTENCY_NOT_PENDING_MESSAGE = "idempotency record is not pending"

_SELECT_BY_SCOPE_SQL = (
    "SELECT * FROM idempotency_records"
    " WHERE organization_id = ? AND actor_id = ? AND operation = ? AND key = ?"
)

_SELECT_BY_ID_SQL = "SELECT * FROM idempotency_records WHERE id = ?"


def _require_operation(operation):
    """Return the stripped operation name, or raise ValidationError."""
    if not isinstance(operation, str) or not operation.strip():
        raise ValidationError("operation must be a non-empty string")
    return operation.strip()


def _require_key(key):
    """Return the stripped idempotency key, or raise ValidationError."""
    if not isinstance(key, str) or not key.strip():
        raise ValidationError("key must be a non-empty string")
    return key.strip()


def _require_actor_id(context):
    """Idempotency scope includes the actor; commands must carry one."""
    if not isinstance(context.actor_id, str) or not context.actor_id:
        raise ValidationError("actor_id required for idempotent commands")
    return context.actor_id


def canonical_request_digest(payload):
    """Canonical sha256 hex digest of the request payload (sorted-key JSON)."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
