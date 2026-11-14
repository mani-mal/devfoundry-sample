"""Work-order transition service for OpsLedger (T027, M4).

Spec §7.4 transitions (the oracle):
    open          -> assigned, cancelled
    assigned      -> in_progress, open, cancelled
    in_progress   -> blocked, completed, cancelled
    blocked       -> in_progress, cancelled
    completed     -> closed, in_progress
    closed        -> open
    cancelled     -> (none)

Each transition checks the expected aggregate version (stale -> retryable
ConflictError). Every state change appends ONE work_order_events row and
ONE audit_events row in the SAME transaction (immutable history; the
application never UPDATEs or DELETEs events). Cancel/block/unblock require
a reason; replaying an already-applied transition with the same key and
payload is rejected with a conflict (no duplicate event rows).
"""

from __future__ import annotations

import json
import sqlite3
from uuid import uuid4

from opsledger.core.clock import Clock, format_rfc3339
from opsledger.core.context import require_context, require_owned
from opsledger.core.db import transaction
from opsledger.core.errors import ConflictError, NotFoundError, ValidationError

__all__ = [
    "WORK_ORDER_TRANSITIONS",
    "TRANSITION_REASON_REQUIRED_MESSAGE",
    "INVALID_TRANSITION_MESSAGE",
    "STALE_WORK_ORDER_VERSION_MESSAGE",
    "transition_work_order",
]

WORK_ORDER_TRANSITIONS = {
    "open": ("assigned", "cancelled"),
    "assigned": ("in_progress", "open", "cancelled"),
    "cancelled": (),
    "in_progress": ("blocked", "completed", "cancelled"),
    "blocked": ("in_progress", "cancelled"),
    "completed": ("closed", "in_progress"),
    "closed": ("open",),
}

TRANSITION_REASON_REQUIRED_MESSAGE = "a reason is required for this transition"
INVALID_TRANSITION_MESSAGE = "transition is not allowed from the current state"
STALE_WORK_ORDER_VERSION_MESSAGE = "work order version conflict; refresh and retry"

_SELECT_WORK_ORDER_SQL = "SELECT * FROM work_orders WHERE id = ?"

_REASONS_REQUIRED = frozenset({"cancelled", "blocked"})
