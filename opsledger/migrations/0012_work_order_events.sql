-- Migration 0012: work-order events storage (T027, M4).
-- Immutable status history: one row per transition (INSERT-only, no
-- UPDATE/DELETE paths anywhere in the application). The composite FKs
-- mirror 0010/0011.

CREATE TABLE work_order_events (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    work_order_id TEXT NOT NULL,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    reason TEXT,
    actor_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (organization_id, work_order_id) REFERENCES work_orders (organization_id, id)
);

CREATE INDEX work_order_events_wo_idx
    ON work_order_events (organization_id, work_order_id);
