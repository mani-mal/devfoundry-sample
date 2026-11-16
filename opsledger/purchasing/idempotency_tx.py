"""Shared idempotency resolution for M6 commands (T044, T045).

Scope per spec 7.3: organization + actor + operation + key. A replayed
command produces ONE business effect. The flow for every M6 command:

1. :func:`begin_or_replay` resolves the record BEFORE the business
   transaction (begin_idempotency runs its own IMMEDIATE transaction,
   so racing begins serialize: the loser sees the winner's committed
   row and replays it). A completed prior command returns its stored
   result for replay; a different payload is a 409 conflict.
2. The caller runs the business writes in ONE transaction and marks
   the record completed INSIDE it with :func:`complete_in_tx` (the
   caller owns the open transaction; no nested BEGIN). This is the
   spec 7.5 contract: the business rows, audit, and the idempotency
   record complete atomically.
3. On business failure the caller marks the record failed with
   core.fail_idempotency (terminal; a retry needs a NEW key) and
   re-raises.
"""

from __future__ import annotations

import json

from opsledger.core.clock import Clock, format_rfc3339
from opsledger.core.context import require_context, require_owned
from opsledger.core.db import transaction
from opsledger.core.errors import ConflictError, ValidationError
from opsledger.core.idempotency import (
    IDEMPOTENCY_DIGEST_CONFLICT_MESSAGE,
    IDEMPOTENCY_NOT_PENDING_MESSAGE,
    begin_idempotency,
)

__all__ = [
    "IDEMPOTENCY_IN_PROGRESS_MESSAGE",
    "IDEMPOTENCY_FAILED_MESSAGE",
    "begin_or_replay",
    "complete_in_tx",
]

IDEMPOTENCY_IN_PROGRESS_MESSAGE = (
    "an identical command is still in progress; retry with the current state"
)

IDEMPOTENCY_FAILED_MESSAGE = (
    "this command previously failed; retry with a new idempotency key"
)

_SELECT_BY_ID_SQL = "SELECT * FROM idempotency_records WHERE id = ?"


def begin_or_replay(conn, context, *, operation, key, request_payload, clock):
    """Resolve the idempotency record for one command.

    Returns (record, replay_result). replay_result is None when the
    caller must perform the business writes (a fresh pending record or
    a re-begun one); otherwise it is the stored JSON result of the
    prior completed command and the caller performs NO business
    writes. A different payload for the same key raises ConflictError
    (409) with the original effect preserved; a pending record (a
    concurrent identical command) and a failed record are retryable
    conflicts.
    """
    record, replayed = begin_idempotency(
        conn, context, operation=operation, key=key,
        request_payload=request_payload, clock=clock,
    )
    if not replayed:
        return record, None
    if record["status"] == "completed":
        return record, json.loads(record["result_payload"])
    if record["status"] == "pending":
        raise ConflictError(IDEMPOTENCY_IN_PROGRESS_MESSAGE)
    return record, (_ for _ in ()).throw(ConflictError(IDEMPOTENCY_FAILED_MESSAGE))


def complete_in_tx(tx, context, *, record_id, result_payload, clock):
    """Complete one pending idempotency record on the caller's transaction.

    The SAME UPDATE contract as core.complete_idempotency executed on
    the caller's open transaction WITHOUT opening a nested one: the
    business rows, the audit records, and this completion commit
    atomically. Completing a record that is not pending raises
    ConflictError.
    """
    require_context(context)
    if not isinstance(result_payload, dict):
        raise ValidationError("result payload must be a dict")
    try:
        payload_text = json.dumps(result_payload, sort_keys=True, separators=(",", ":"))
    except TypeError:
        raise ValidationError("result payload must be JSON-serializable") from None
    timestamp_text = format_rfc3339(clock.now())
    row = tx.execute(_SELECT_BY_ID_SQL, (record_id,)).fetchone()
    require_owned(context, row, label="idempotency record")
    updated = tx.execute(
        "UPDATE idempotency_records SET status = 'completed', result_payload = ?,"
        " updated_at = ?, completed_at = ? WHERE id = ? AND status = 'pending'",
        (payload_text, timestamp_text, timestamp_text, record_id),
    ).rowcount
    if updated != 1:
        raise ConflictError(IDEMPOTENCY_NOT_PENDING_MESSAGE)
    return tx.execute(_SELECT_BY_ID_SQL, (record_id,)).fetchone()
