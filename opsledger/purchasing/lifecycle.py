"""Purchase-request lifecycle (T042, part 2 of 2): submit, cancel, decisions.

Business rules live here in the domain service -- never in HTTP
adapters. Each transition is validated before it is applied, and every
accepted change writes the guarded request UPDATE plus the audit record
in ONE explicit transaction (atomically; sqlite3 errors are mapped as
documented). Submit and cancel never touch approvals. Approve and
reject are valid only from 'submitted', require a live 'approver'
membership row, and refuse the requester even when their own role is
'approver'. Unknown and cross-organization ids surface one canonical
message: no existence leak.
"""

from __future__ import annotations

import sqlite3
from uuid import uuid4

from opsledger.core.clock import format_rfc3339
from opsledger.core.context import require_context, require_owned
from opsledger.core.db import transaction
from opsledger.core.errors import ConflictError, ValidationError
from opsledger.core.errors import PermissionDeniedError

__all__ = [
    "SELF_APPROVAL_MESSAGE",
    "APPROVER_PERMISSION_MESSAGE",
    "submit_purchase_request",
    "cancel_purchase_request",
    "approve_purchase_request",
    "reject_purchase_request",
]

SELF_APPROVAL_MESSAGE = "the requester cannot approve their own purchase request"

APPROVER_PERMISSION_MESSAGE = "purchase.approve permission required"

_SELECT_REQUEST_SQL = "SELECT * FROM purchase_requests WHERE id = ?"

_DRAFT_STATUS = "draft"
_SUBMITTED_STATUS = "submitted"
_APPROVED_STATUS = "approved"
_REJECTED_STATUS = "rejected"
_CANCELLED_STATUS = "cancelled"

_CANCELLABLE_STATUSES = frozenset({_DRAFT_STATUS, _SUBMITTED_STATUS})

_NOT_SUBMITTED_MESSAGE = "purchase request is not submitted"
_CANCELLED_DECISION_MESSAGE = "cancelled purchase request cannot be decided"
_DUPLICATE_APPROVAL_MESSAGE = "duplicate approval for request"
_APPROVAL_ID_PREFIX = "apr-"

_INSERT_APPROVAL_SQL = (
    "INSERT INTO approvals (id, organization_id, purchase_request_id,"
    " approver_id, decision, approved_total_cents, reason, decided_at,"
    " created_at, updated_at, invalidated_at)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)"
)

_SELECT_APPROVER_MEMBERSHIP_SQL = (
    "SELECT 1 FROM memberships"
    " WHERE organization_id = ? AND user_id = ? AND role = 'approver'"
)


def _request(
    conn: object,
    context: object,
    purchase_request_id: object,
) -> object:
    """Return the in-scope request row (require_owned, label purchase request)."""
    require_context(context)
    row = conn.execute(_SELECT_REQUEST_SQL, (purchase_request_id,)).fetchone()
    require_owned(context, row, label="purchase request")
    return row


def _guarded_update(
    tx: object,
    *,
    purchase_request_id: str,
    from_status: str,
    to_status: str,
    expected_version: int,
    total_cents: int,
    timestamp_text: str,
) -> None:
    """Apply the guarded optimistic-concurrency UPDATE (retryable on stale)."""
    cursor = tx.execute(
        "UPDATE purchase_requests SET status = ?, total_cents = ?,"
        " version = version + 1, updated_at = ?"
        " WHERE id = ? AND status = ? AND version = ?",
        (
            to_status,
            total_cents,
            timestamp_text,
            purchase_request_id,
            from_status,
            expected_version,
        ),
    )
    if cursor.rowcount != 1:
        raise ConflictError("purchase request version conflict; refresh and retry")


def _decide(
    conn: object,
    context: object,
    *,
    purchase_request_id: object,
    expected_version: int,
    decision: str,
    clock: object,
    reason: object,
) -> object:
    """Apply one decision to a submitted request (all checks, then write)."""
    request_row = _request(conn, context, purchase_request_id)
    current_status = request_row["status"]
    if current_status == _CANCELLED_STATUS:
        raise ConflictError(_CANCELLED_DECISION_MESSAGE)
    if current_status != _SUBMITTED_STATUS:
        raise ConflictError(_NOT_SUBMITTED_MESSAGE)
    if expected_version != request_row["version"]:
        raise ConflictError("purchase request version conflict; refresh and retry")
    if request_row["requested_by"] == context.actor_id:
        raise PermissionDeniedError(SELF_APPROVAL_MESSAGE)
    approver_row = conn.execute(
        _SELECT_APPROVER_MEMBERSHIP_SQL,
        (context.organization_id, context.actor_id),
    ).fetchone()
    if approver_row is None:
        raise PermissionDeniedError(APPROVER_PERMISSION_MESSAGE)
    cleaned_reason = reason.strip() if isinstance(reason, str) else None
    timestamp_text = format_rfc3339(clock.now())
    approval_id = _APPROVAL_ID_PREFIX + uuid4().hex
    try:
        with transaction(conn) as tx:
            _guarded_update(
                tx,
                purchase_request_id=purchase_request_id,
                from_status=current_status,
                to_status=decision,
                expected_version=expected_version,
                total_cents=request_row["total_cents"],
                timestamp_text=timestamp_text,
            )
            tx.execute(
                _INSERT_APPROVAL_SQL,
                (
                    approval_id,
                    context.organization_id,
                    request_row["id"],
                    context.actor_id,
                    decision,
                    request_row["total_cents"],
                    cleaned_reason,
                    timestamp_text,
                    timestamp_text,
                    timestamp_text,
                ),
            )
            from opsledger.audit import record_event_in_tx
            record_event_in_tx(
                tx,
                context,
                entity_type="purchase_request",
                entity_id=request_row["id"],
                operation="purchase_request." + ("approved" if decision == _APPROVED_STATUS else "rejected"),
                details={
                    "from_status": current_status,
                    "to_status": decision,
                    "from_version": expected_version,
                    "to_version": expected_version + 1,
                    "approval_id": approval_id,
                },
                clock=clock,
            )
    except sqlite3.IntegrityError as exc:
        raise ConflictError(_DUPLICATE_APPROVAL_MESSAGE) from exc
    return conn.execute(_SELECT_REQUEST_SQL, (purchase_request_id,)).fetchone()


def approve_purchase_request(conn, context, *, purchase_request_id, expected_version, clock, reason=None):
    """Approve one submitted request (approver membership required)."""
    return _decide(
        conn,
        context,
        purchase_request_id=purchase_request_id,
        expected_version=expected_version,
        decision=_APPROVED_STATUS,
        clock=clock,
        reason=reason,
    )


def reject_purchase_request(conn, context, *, purchase_request_id, expected_version, clock, reason=None):
    """Reject one submitted request (approver membership required)."""
    return _decide(
        conn,
        context,
        purchase_request_id=purchase_request_id,
        expected_version=expected_version,
        decision=_REJECTED_STATUS,
        clock=clock,
        reason=reason,
    )


def submit_purchase_request(conn, context, *, purchase_request_id, expected_version, clock):
    """Submit one draft request: draft -> submitted (stores recomputed total)."""
    request_row = _request(conn, context, purchase_request_id)
    current_status = request_row["status"]
    if current_status != _DRAFT_STATUS:
        raise ConflictError("purchase request is not draft")
    line_rows = [
        row
        for row in conn.execute(
            "SELECT * FROM purchase_request_lines"
            " WHERE purchase_request_id = ? AND organization_id = ?"
            " ORDER BY created_at, id",
            (request_row["id"], context.organization_id),
        ).fetchall()
        if row["archived_at"] is None
    ]
    total_cents = sum(line["quantity"] * line["unit_cost_cents"] for line in line_rows)
    if total_cents <= 0:
        raise ValidationError("purchase request has no lines")
    timestamp_text = format_rfc3339(clock.now())
    try:
        with transaction(conn) as tx:
            _guarded_update(
                tx,
                purchase_request_id=request_row["id"],
                from_status=current_status,
                to_status=_SUBMITTED_STATUS,
                expected_version=expected_version,
                total_cents=total_cents,
                timestamp_text=timestamp_text,
            )
            from opsledger.audit import record_event_in_tx
            record_event_in_tx(
                tx,
                context,
                entity_type="purchase_request",
                entity_id=request_row["id"],
                operation="purchase_request.submit",
                details={
                    "from_status": current_status,
                    "to_status": _SUBMITTED_STATUS,
                    "from_version": expected_version,
                    "to_version": expected_version + 1,
                    "total_cents": total_cents,
                },
                clock=clock,
            )
    except sqlite3.IntegrityError as exc:
        raise ConflictError("purchase request version conflict; refresh and retry") from exc
    return conn.execute(_SELECT_REQUEST_SQL, (request_row["id"],)).fetchone()


def cancel_purchase_request(conn, context, *, purchase_request_id, expected_version, clock, reason=None):
    """Cancel one draft or submitted request (any in-scope actor)."""
    request_row = _request(conn, context, purchase_request_id)
    current_status = request_row["status"]
    if current_status not in _CANCELLABLE_STATUSES:
        raise ConflictError("only a draft or submitted request can be cancelled")
    cleaned_reason = reason.strip() if isinstance(reason, str) else None
    timestamp_text = format_rfc3339(clock.now())
    try:
        with transaction(conn) as tx:
            _guarded_update(
                tx,
                purchase_request_id=request_row["id"],
                from_status=current_status,
                to_status=_CANCELLED_STATUS,
                expected_version=expected_version,
                total_cents=request_row["total_cents"],
                timestamp_text=timestamp_text,
            )
            from opsledger.audit import record_event_in_tx
            record_event_in_tx(
                tx,
                context,
                entity_type="purchase_request",
                entity_id=request_row["id"],
                operation="purchase_request.cancel",
                details={
                    "from_status": current_status,
                    "to_status": _CANCELLED_STATUS,
                    "from_version": expected_version,
                    "to_version": expected_version + 1,
                    "reason": cleaned_reason,
                },
                clock=clock,
            )
    except sqlite3.IntegrityError as exc:
        raise ConflictError("purchase request version conflict; refresh and retry") from exc
    return conn.execute(_SELECT_REQUEST_SQL, (request_row["id"],)).fetchone()
