-- Migration 0016: parts and stock-location storage (T033, M5).
-- Scoped uniqueness per spec M5/T033: SKU unique within organization,
-- location code unique within organization (same SKU/code in another
-- organization is allowed). Composite FKs mirror 0010. Soft deletion:
-- archived_at NULL now, archive lands in a later task.

CREATE TABLE parts (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    sku TEXT NOT NULL,
    name TEXT NOT NULL,
    unit_of_measure TEXT NOT NULL,
    standard_cost_cents INTEGER NOT NULL CHECK (standard_cost_cents >= 0),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    UNIQUE (organization_id, sku)
);

CREATE TABLE stock_locations (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    UNIQUE (organization_id, code)
);

CREATE INDEX parts_org_idx ON parts (organization_id);

CREATE INDEX stock_locations_org_idx ON stock_locations (organization_id);
