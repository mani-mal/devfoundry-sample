-- Migration 0017: stock balance and movement ledger storage (T034, M5).
-- One balance row per (part, location) — the partial unique index enforces
-- exactly one balance per pair. The movement ledger is the accounting
-- source: one row per operation (INSERT-only, no UPDATE/DELETE paths
-- anywhere in the application). Composite FKs mirror 0016; the
-- (organization_id, id) unique indexes on parts/stock_locations back
-- those composite FKs exactly like work_orders_org_id_idx in 0011.
-- Tables are created before their indexes.

CREATE TABLE stock_balances (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    part_id TEXT NOT NULL,
    stock_location_id TEXT NOT NULL,
    on_hand INTEGER NOT NULL DEFAULT 0 CHECK (on_hand >= 0),
    reserved INTEGER NOT NULL DEFAULT 0 CHECK (reserved >= 0),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (organization_id, part_id) REFERENCES parts (organization_id, id),
    FOREIGN KEY (organization_id, stock_location_id) REFERENCES stock_locations (organization_id, id)
);

CREATE TABLE stock_movements (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    part_id TEXT NOT NULL,
    stock_location_id TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('receive', 'reserve', 'release', 'consume', 'adjust')),
    on_hand_delta INTEGER NOT NULL,
    reserved_delta INTEGER NOT NULL,
    reason TEXT,
    work_order_id TEXT,
    actor_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (organization_id, part_id) REFERENCES parts (organization_id, id),
    FOREIGN KEY (organization_id, stock_location_id) REFERENCES stock_locations (organization_id, id)
);

CREATE UNIQUE INDEX parts_org_id_idx ON parts (organization_id, id);

CREATE UNIQUE INDEX stock_locations_org_id_idx
    ON stock_locations (organization_id, id);

CREATE UNIQUE INDEX stock_balances_org_part_loc_idx
    ON stock_balances (organization_id, part_id, stock_location_id);

CREATE INDEX stock_movements_ledger_idx
    ON stock_movements (organization_id, part_id, stock_location_id);

CREATE INDEX stock_balances_org_idx ON stock_balances (organization_id);
