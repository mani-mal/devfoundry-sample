-- Migration 0013: work-order checklist storage (T028, M4).
-- One row per checklist item; completion stamps completed_at. The composite
-- FK mirrors 0011/0012 (cross-organization references impossible to store).

CREATE TABLE checklist_items (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    work_order_id TEXT NOT NULL,
    label TEXT NOT NULL,
    mandatory INTEGER NOT NULL DEFAULT 0 CHECK (mandatory IN (0, 1)),
    completed_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (organization_id, work_order_id) REFERENCES work_orders (organization_id, id)
);

CREATE INDEX checklist_items_wo_idx
    ON checklist_items (organization_id, work_order_id);
