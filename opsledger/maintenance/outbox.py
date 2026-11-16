"""Maintenance outbox module for OpsLedger: persisted pending-run processing
with bounded retry (T052, module).

Each PENDING maintenance run is re-driven through work-order creation and
completed in ONE transaction per run; the same transaction writes the run
row and its outbox record, so a simulated crash at ANY point creates no
duplicate work order and never leaves the persisted trail inconsistent.

Processing is LOCAL: nothing is delivered outside the application (no
network, no email). Outbox rows are SYNTHETIC in-app notification records -
the persisted audit/observability trail of the maintenance run.

Every lookup carries the authenticated organization context: the processor
only ever touches runs of its own organization - one canonical error
message, no existence leak (IDs are not authorization).
"""

from __future__ import annotations

from datetime import timedelta

from opsledger.audit import record_event_in_tx
from opsledger.core.clock import format_rfc3339
from opsledger.core.context import require_context, require_owned, scoped_all
from opsledger.core.db import transaction
from opsledger.core.errors import ConflictError, ValidationError
from opsledger.workorders import create_work_order

__all__ = [
    "OUTBOX_RECORD_MESSAGE",
    "RETRY_EXHAUSTED_MESSAGE",
    "RUN_NOT_FOUND_MESSAGE",
    "outbox_events_for_run",
    "process_pending_runs",
]

OUTBOX_RECORD_MESSAGE = "maintenance run processed"

RUN_NOT_FOUND_MESSAGE = "maintenance run not found"

RETRY_EXHAUSTED_MESSAGE = "maintenance run retry limit reached"

_SELECT_PENDING_RUNS_SQL = (
    "SELECT mr.id, mr.organization_id, mr.plan_id, mr.scheduled_date,"
    " mr.status, mr.work_order_id, mr.attempt_count, mr.next_retry_at,"
    " mr.last_error, mp.name AS plan_name, mp.site_id, mp.asset_id"
    " FROM maintenance_runs mr JOIN maintenance_plans mp"
    " ON mp.id = mr.plan_id"
    " WHERE mr.organization_id = ? AND mr.status = 'pending'"
    " AND (mr.next_retry_at IS NULL OR mr.next_retry_at <="
    " strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"
    " ORDER BY mr.scheduled_date, mr.id"
)


def _pending_runs(conn, context):
    """SELECT the due pending maintenance runs for the authenticated organization."""
    return scoped_all(conn, context, _SELECT_PENDING_RUNS_SQL, (context.organization_id,))


def _update_run_sql(columns: str) -> str:
    """Build the single-run UPDATE for the given SET columns."""
    return f"UPDATE maintenance_runs SET {columns} WHERE id = ?"


def process_pending_runs(conn, context, *, actor_id, clock, max_attempts=3):
    """Re-drive due pending maintenance runs, one transaction per run.

    The pending->generated transition plus the maintenance_runs UNIQUE key
    mean a simulated crash at ANY point creates no duplicate work order: a
    retry after the work-order INSERT finds the duplicate number and
    idempotently completes the run.
    """
    context = require_context(context)
    if not isinstance(actor_id, str) or not actor_id.strip():
        raise ValidationError("actor_id must be a non-blank string")
    processed = []
    for run in _pending_runs(conn, context):
        attempt_count = run["attempt_count"]
        if attempt_count >= max_attempts:
            with transaction(conn) as tx:
                tx.execute(
                    _update_run_sql("status = 'failed', last_error = ?, updated_at = ?"),
                    (RETRY_EXHAUSTED_MESSAGE, format_rfc3339(clock.now()), run["id"]),
                )
            continue
        try:
            work_order_id = run["work_order_id"]
            if work_order_id is None:
                number = "M-" + run["plan_id"] + "-" + run["scheduled_date"]
                try:
                    created = create_work_order(
                        conn,
                        context,
                        site_id=run["site_id"],
                        asset_id=run["asset_id"],
                        number=number,
                        title="Maintenance: " + run["plan_name"],
                        description=number,
                        priority="medium",
                        requester_id=actor_id,
                        clock=clock,
                    )
                except ConflictError:
                    existing = conn.execute(
                        "SELECT id FROM work_orders"
                        " WHERE organization_id = ? AND number = ?",
                        (context.organization_id, number),
                    ).fetchone()
                    work_order_id = existing["id"]
                else:
                    work_order_id = created["id"]
            attempt = attempt_count + 1
            with transaction(conn) as tx:
                tx.execute(
                    _update_run_sql(
                        "status = 'generated', work_order_id = ?,"
                        " attempt_count = ?, last_error = NULL,"
                        " next_retry_at = NULL, updated_at = ?"
                    ),
                    (work_order_id, attempt, format_rfc3339(clock.now()), run["id"]),
                )
                record_event_in_tx(
                    tx,
                    context,
                    entity_type="maintenance_run",
                    entity_id=run["id"],
                    operation="maintenance.run_processed",
                    details={
                        "work_order_id": work_order_id,
                        "scheduled_date": run["scheduled_date"],
                        "attempt": attempt,
                    },
                    clock=clock,
                )
        except BaseException as exc:
            with transaction(conn) as tx:
                tx.execute(
                    _update_run_sql(
                        "status = 'pending', attempt_count = ?,"
                        " last_error = ?, next_retry_at = ?"
                    ),
                    (
                        attempt_count + 1,
                        str(exc)[:200],
                        format_rfc3339(clock.now() + timedelta(seconds=60)),
                        run["id"],
                    ),
                )
            continue
        processed.append(
            {
                "run_id": run["id"],
                "work_order_id": work_order_id,
                "scheduled_date": run["scheduled_date"],
                "attempt": attempt,
            }
        )
    return processed


def outbox_events_for_run(conn, context, *, run_id):
    """Expose the persisted outbox trail of one maintenance run, oldest first."""
    run = conn.execute(
        "SELECT id, organization_id FROM maintenance_runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    require_owned(context, run, label="maintenance run")
    return scoped_all(
        conn,
        context,
        "SELECT id, organization_id, actor_id, entity_type, entity_id,"
        " operation, details, created_at FROM audit_events"
        " WHERE organization_id = ? AND entity_type = 'maintenance_run'"
        " AND entity_id = ? ORDER BY created_at, id",
        (context.organization_id, run_id),
    )
