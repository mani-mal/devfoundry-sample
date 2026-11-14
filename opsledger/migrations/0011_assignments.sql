-- Migration 0011: work-order assignments storage (T026, M4).
-- One ACTIVE assignment per work order (partial unique index); released
-- assignments keep the history. The composite foreign keys make cross-
-- organization work-order/site references impossible to store (same
-- mechanism as 0010).

CREATE UNIQUE INDEX work_orders_org_id_idx ON work_orders (organization_id, id);

CREATE TABLE assignments (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    work_order_id TEXT NOT NULL,
    site_id TEXT NOT NULL,
    technician_id TEXT NOT NULL REFERENCES users(id),
    assigned_by_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    released_at TEXT,
    FOREIGN KEY (organization_id, work_order_id) REFERENCES work_orders (organization_id, id),
    FOREIGN KEY (organization_id, site_id) REFERENCES sites (organization_id, id)
);

CREATE UNIQUE INDEX assignments_active_org_wo_idx
    ON assignments (organization_id, work_order_id)
    WHERE released_at IS NULL;

CREATE INDEX assignments_technician_idx
    ON assignments (organization_id, technician_id);
