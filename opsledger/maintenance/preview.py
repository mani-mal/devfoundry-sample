"""Due-date preview for maintenance plans (T050, module).

Deterministic due-date preview for one owned, active maintenance plan.
The ONLY time source is the injected clock: this module never calls
datetime.now() or date.today(), so month/year/leap-day boundaries are
byte-identical under fixed clock fixtures. All scheduling math is UTC
dates (datetime.date).

The anchor is the plan's created_at UTC date. Due dates repeat every
interval_days starting at the anchor, while each candidate stays within
the bounded horizon: clock.now() + horizon_days calendar days. The
result is capped at 366 entries, so no loop is unbounded.
"""

from __future__ import annotations

from datetime import date, timedelta

from opsledger.core.context import require_owned
from opsledger.core.errors import ConflictError

__all__ = [
    "PLAN_NOT_ACTIVE_MESSAGE",
    "preview_due_dates",
    "next_due_date",
]

PLAN_NOT_ACTIVE_MESSAGE = "maintenance plan is not active"

MAX_PREVIEW_ENTRIES = 366


def _require_utc_date(text):
    """Return the UTC date of an RFC3339 Z text (its first 10 characters)."""
    return date.fromisoformat(str(text)[:10])


def _date_only(value):
    """Return the UTC date of a timezone-aware datetime."""
    return date(value.year, value.month, value.day)


def _fetch_owned_plan(conn, context, plan_id):
    """Fetch one plan by id and enforce ownership and active state."""
    row = conn.execute(
        "SELECT * FROM maintenance_plans WHERE id = ?", (plan_id,)
    ).fetchone()
    row = require_owned(context, row, label="maintenance plan")
    if row["active"] != 1 or row["archived_at"] is not None:
        raise ConflictError(PLAN_NOT_ACTIVE_MESSAGE)
    return row


def _collect_due_dates(plan, now_utc):
    """Return the bounded, ascending preview dates for one active plan."""
    anchor = _require_utc_date(plan["created_at"])
    horizon = _date_only(now_utc) + timedelta(days=plan["horizon_days"])
    step = timedelta(days=plan["interval_days"])
    due_dates = []
    k = 0
    while len(due_dates) < MAX_PREVIEW_ENTRIES:
        candidate = anchor + k * step
        if candidate > horizon:
            break
        due_dates.append(candidate)
        k += 1
    return due_dates


def preview_due_dates(conn, context, *, plan_id, clock):
    """Return the due dates for one plan as ascending UTC date texts.

    The anchor is the plan's created_at UTC date. Each candidate is
    anchor + k * interval_days for k = 0, 1, 2, ... while it stays
    within the bounded horizon clock.now() + horizon_days calendar
    days. At most 366 entries are returned, so the loop is bounded even
    if the horizon bound could never otherwise be reached.
    """
    plan = _fetch_owned_plan(conn, context, plan_id)
    return [d.isoformat() for d in _collect_due_dates(plan, clock.now())]


def next_due_date(conn, context, *, plan_id, clock):
    """Return the next occurrence for one plan as a UTC date text.

    The next occurrence is the first previewed date strictly after the
    clock's current instant. When every previewed date is in the past,
    the next date after the last previewed one is returned instead, so
    the result is always the next occurrence. Boundary dates never
    raise: month/year/leap-day transitions are produced by datetime
    date arithmetic and are inherently correct.
    """
    plan = _fetch_owned_plan(conn, context, plan_id)
    now_utc = clock.now()
    today = _date_only(now_utc)
    due_dates = _collect_due_dates(plan, now_utc)
    for candidate in due_dates:
        if candidate > today:
            return candidate.isoformat()
    k_max = len(due_dates) - 1
    step = timedelta(days=plan["interval_days"])
    anchor = _require_utc_date(plan["created_at"])
    next_after_last = anchor + (k_max + 1) * step
    return next_after_last.isoformat()
