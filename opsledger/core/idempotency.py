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


def begin_idempotency(conn, context, *, operation, key, request_payload, clock):
    """Begin (or resolve) one idempotency record; returns (record, replayed).

    require_context(context) plus a non-empty actor_id (the scope includes
    the actor); operation and key must be non-empty strings; the request
    payload must be JSON-serializable (its canonical digest is stored).
    When a record already exists for the scope, the same digest returns
    the prior record with replayed=True and the caller replays its stored
    result; a different digest raises ConflictError (HTTP 409) and the
    original record is untouched. A new scope inserts one pending row
    inside one transaction and returns it with replayed=False.
    """
    context = require_context(context)
    actor_id = _require_actor_id(context)
    validated_operation = _require_operation(operation)
    validated_key = _require_key(key)
    try:
        request_digest = canonical_request_digest(request_payload)
    except TypeError:
        raise ValidationError("request payload must be JSON-serializable") from None
    timestamp_text = format_rfc3339(clock.now())
    with transaction(conn) as tx:
        row = tx.execute(
            _SELECT_BY_SCOPE_SQL,
            (context.organization_id, actor_id, validated_operation, validated_key),
        ).fetchone()
        if row is not None:
            if row["request_digest"] != request_digest:
                raise ConflictError(IDEMPOTENCY_DIGEST_CONFLICT_MESSAGE)
            return row, True
        record_id = "idm-" + uuid4().hex
        tx.execute(
            "INSERT INTO idempotency_records (id, organization_id, actor_id, operation,"
            " key, request_digest, status, result_payload, created_at, updated_at,"
            " completed_at) VALUES (?, ?, ?, ?, ?, ?, 'pending', NULL, ?, ?, NULL)",
            (
                record_id,
                context.organization_id,
                actor_id,
                validated_operation,
                validated_key,
                request_digest,
                timestamp_text,
                timestamp_text,
            ),
        )
    return conn.execute(_SELECT_BY_ID_SQL, (record_id,)).fetchone(), False


def complete_idempotency(conn, context, *, record_id, result_payload, clock):
    """Mark one pending record completed with its replayable result payload.

    require_owned lookup (missing and cross-organization surface the same
    NotFoundError); the result payload must be a JSON-serializable dict and
    is stored as canonical JSON. Completing a record that is not pending
    raises ConflictError (completed and failed are terminal).
    """
    require_context(context)
    if not isinstance(result_payload, dict):
        raise ValidationError("result payload must be a dict")
    try:
        payload_text = json.dumps(result_payload, sort_keys=True, separators=(",", ":"))
    except TypeError:
        raise ValidationError("result payload must be JSON-serializable") from None
    timestamp_text = format_rfc3339(clock.now())
    with transaction(conn) as tx:
        row = tx.execute(_SELECT_BY_ID_SQL, (record_id,)).fetchone()
        require_owned(context, row, label="idempotency record")
        updated = tx.execute(
            "UPDATE idempotency_records SET status = 'completed', result_payload = ?,"
            " updated_at = ?, completed_at = ? WHERE id = ? AND status = 'pending'",
            (payload_text, timestamp_text, timestamp_text, record_id),
        ).rowcount
        if updated != 1:
            raise ConflictError(IDEMPOTENCY_NOT_PENDING_MESSAGE)
    return conn.execute(_SELECT_BY_ID_SQL, (record_id,)).fetchone()


def fail_idempotency(conn, context, *, record_id, clock):
    """Mark one pending record failed (terminal; a retry needs a new key).

    require_owned lookup (missing and cross-organization surface the same
    NotFoundError); the result payload stays NULL. Failing a record that
    is not pending raises ConflictError.
    """
    require_context(context)
    timestamp_text = format_rfc3339(clock.now())
    with transaction(conn) as tx:
        row = tx.execute(_SELECT_BY_ID_SQL, (record_id,)).fetchone()
        require_owned(context, row, label="idempotency record")
        updated = tx.execute(
            "UPDATE idempotency_records SET status = 'failed', updated_at = ?,"
            " completed_at = ? WHERE id = ? AND status = 'pending'",
            (timestamp_text, timestamp_text, record_id),
        ).rowcount
        if updated != 1:
            raise ConflictError(IDEMPOTENCY_NOT_PENDING_MESSAGE)
    return conn.execute(_SELECT_BY_ID_SQL, (record_id,)).fetchone()


def get_idempotency_record(conn, context, *, record_id):
    """Return one idempotency record in scope, or NotFoundError (no leak)."""
    require_context(context)
    row = conn.execute(_SELECT_BY_ID_SQL, (record_id,)).fetchone()
    return require_owned(context, row, label="idempotency record")
