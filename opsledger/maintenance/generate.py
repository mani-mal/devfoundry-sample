"""Idempotent due-work-order generation for maintenance plans (T051, module).

Generates one work order per due scheduled date of every ACTIVE
maintenance plan in the authenticated organization. The generation
idempotency key is (organization, plan, scheduled_date) - the
maintenance_runs UNIQUE key - so the same plan and date produce ONE
work order, including concurrent calls: racing run INSERTs serialize
on the UNIQUE key, and only runs still 'pending' reach work-order
creation.

The pending->generated status transition plus the maintenance_runs
UNIQUE key IS the idempotency mechanism: a second generate call finds
the run already 'generated' and skips it. A work-order INSERT that
fails leaves the run 'pending' with attempt_count incremented and
last_error set, so the caller can retry it without duplicates.

The ONLY time source is the injected clock: this module never calls
datetime.now() or date.today(), so month/year/leap-day boundaries are
byte-identical under fixed clock fixtures. All scheduling math is UTC
dates and timestamps are canonical RFC3339 Z text. Writes happen in
one explicit transaction per plan-date pair.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from uuid import uuid4

from opsledger.core.clock import format_rfc3339
from opsledger.core.context import require_context, require_owned
from opsledger.core.db import transaction
from opsledger.core.errors import ConflictError, ValidationError
from opsledger.maintenance.plans import list_maintenance_plans
from opsledger.maintenance.preview import preview_due_dates
from opsledger.workorders import create_work_order

__all__ = [
    "PLAN_NOT_ACTIVE_MESSAGE",
    "RUN_NOT_FOUND_MESSAGE",
    "generate_due_work_orders",
    "get_run",
]

PLAN_NOT_ACTIVE_MESSAGE = "maintenance plan is not active"
RUN_NOT_FOUND_MESSAGE = "maintenance run not found"

_MAX_PREVIEW_ENTRIES = 366
_MAX_ATTEMPTS = 3

_SELECT_RUN_SQL = (
    "SELECT * FROM maintenance_runs"
    " WHERE organization_id = ? AND plan_id = ? AND scheduled_date = ?"
)


def _require_positive_int(value, message):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValidationError(message)
    return value


def _utc_date(value):
    """Return the UTC date of an aware datetime or RFC3339 text."""
    if isinstance(value, str):
        return date.fromisoformat(str(value)[:10])
    return date(value.year, value.month, value.day)


def _due_dates(conn, context, plan, clock, horizon_days):
    """Return the bounded, ascending generation dates for one active plan."""
    bound = plan["horizon_days"]
    if horizon_days is not None:
        bound = min(_require_positive_int(horizon_days, "horizon_days must be a positive integer"), bound)
    horizon_end = _utc_date(clock.now()) + timedelta(days=bound)
    dates = []
    for text in preview_due_dates(conn, context, plan_id=plan["id"], clock=clock):
        candidate = date.fromisoformat(text)
        if candidate > horizon_end:
            break
        dates.append(candidate)
    return dates


def _ensure_run(conn, context, plan_id, scheduled_date, timestamp_text):
    """Ensure the persisted run exists for one plan and scheduled date.

    The run INSERT happens inside ONE explicit transaction per plan-date
    pair; the UNIQUE (organization_id, plan_id, scheduled_date) key races
    with a concurrent INSERT, so an IntegrityError is treated as existing:
    the row is re-selected and NOT raised.
    """
    run = conn.execute(_SELECT_RUN_SQL, (context.organization_id, plan_id, scheduled_date)).fetchone()
    if run is not None:
        return run
    try:
        with transaction(conn) as tx:
            tx.execute(
                "INSERT INTO maintenance_runs (id, organization_id, plan_id,"
                " scheduled_date, work_order_id, status, attempt_count, last_error,"
                " next_retry_at, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, NULL, 'pending', 0, NULL, NULL, ?, ?)",
                ("mrun-" + uuid4().hex, context.organization_id, plan_id, scheduled_date, timestamp_text, timestamp_text),
            )
    except sqlite3.IntegrityError:
        run = conn.execute(_SELECT_RUN_SQL, (context.organization_id, plan_id, scheduled_date)).fetchone()
        if run is None:
            raise
        return run
    return conn.execute(_SELECT_RUN_SQL, (context.organization_id, plan_id, scheduled_date)).fetchone()


def _mark_run_failed(conn, run, clock, error_text):
    """Transition one run to 'failed' after its retry budget is consumed."""
    timestamp_text = format_rfc3339(clock.now())
    with transaction(conn) as tx:
        tx.execute(
            "UPDATE maintenance_runs SET status = 'failed', last_error = ?,"
            " updated_at = ? WHERE id = ?",
            (error_text, timestamp_text, run["id"]),
        )


def _generate_for_plan(conn, context, plan, clock, horizon_days, actor_id):
    """Generate work orders for the due scheduled dates of one active plan."""
    created = []
    timestamp_text = format_rfc3339(clock.now())
    for scheduled_date in _due_dates(conn, context, plan, clock, horizon_days):
        date_text = scheduled_date.isoformat()
        if scheduled_date > _utc_date(clock.now()):
            continue
        run = _ensure_run(conn, context, plan["id"], date_text, timestamp_text)
        if run["status"] != "pending":
            continue
        if run["attempt_count"] >= _MAX_ATTEMPTS:
            _mark_run_failed(conn, run, clock, run["last_error"] or "maintenance run retry limit reached")
            continue
        number = "M-" + plan["id"] + "-" + date_text
        try:
            work_order = create_work_order(
                conn,
                context,
                site_id=plan["site_id"],
                asset_id=plan["asset_id"],
                number=number,
                title="Maintenance: " + plan["name"],
                description=plan["description"],
                priority="medium",
                requester_id=actor_id,
                clock=clock,
            )
        except ConflictError:
            existing = conn.execute(
                "SELECT work_order_id FROM maintenance_runs"
                " WHERE organization_id = ? AND plan_id = ? AND scheduled_date = ?",
                (context.organization_id, plan["id"], date_text),
            ).fetchone()
            work_order_id = existing["work_order_id"]
            if work_order_id is None:
                lookup = conn.execute(
                    "SELECT id FROM work_orders WHERE organization_id = ? AND number = ?",
                    (context.organization_id, number),
                ).fetchone()
                work_order_id = lookup["id"]
            with transaction(conn) as tx:
                tx.execute(
                    "UPDATE maintenance_runs SET status = 'generated',"
                    " work_order_id = ?, attempt_count = attempt_count + 1,"
                    " updated_at = ? WHERE id = ?",
                    (work_order_id, format_rfc3339(clock.now()), run["id"]),
                )
            created.append(
                {
                    "run_id": run["id"],
                    "work_order_id": work_order_id,
                    "scheduled_date": date_text,
                }
            )
        except Exception as exc:
            with transaction(conn) as tx:
                tx.execute(
                    "UPDATE maintenance_runs SET status = 'pending',"
                    " attempt_count = attempt_count + 1, last_error = ?,"
                    " updated_at = ? WHERE id = ?",
                    (str(exc)[:200], format_rfc3339(clock.now()), run["id"]),
                )
            continue
        else:
            with transaction(conn) as tx:
                tx.execute(
                    "UPDATE maintenance_runs SET status = 'generated',"
                    " work_order_id = ?, attempt_count = attempt_count + 1,"
                    " updated_at = ? WHERE id = ?",
                    (work_order["id"], format_rfc3339(clock.now()), run["id"]),
                )
            created.append(
                {
                    "run_id": run["id"],
                    "work_order_id": work_order["id"],
                    "scheduled_date": date_text,
                }
            )
    return created


def generate_due_work_orders(conn, context, *, actor_id, clock, horizon_days=None):
    """Generate work orders for the due scheduled dates of every active plan.

    Returns one dict per work order CREATED by this call, each exactly
    {"run_id", "work_order_id", "scheduled_date"}, in ascending
    scheduled_date order. Runs already 'generated' or 'failed' are skipped.
    """
    context = require_context(context)
    if not isinstance(actor_id, str) or not actor_id.strip():
        raise ValidationError("actor_id must be a non-blank string")
    created = []
    for plan in list_maintenance_plans(conn, context, active_only=True):
        created.extend(_generate_for_plan(conn, context, plan, clock, horizon_days, actor_id))
    return sorted(
        created,
        key=lambda entry: (entry["scheduled_date"], entry["run_id"]),
    )


def get_run(conn, context, *, run_id):
    """Return one owned maintenance run row or raise NotFoundError (no leak)."""
    run = conn.execute(
        "SELECT * FROM maintenance_runs WHERE id = ?", (run_id,)
    ).fetchone()
    return require_owned(context, run, label="maintenance run")
