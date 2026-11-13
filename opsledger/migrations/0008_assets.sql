-- Migration 0008: assets storage with database-level site scoping (T018, M3).
-- The unique index on sites (organization_id, id) backs the composite foreign
-- key on assets: an asset row's (organization_id, site_id) must match a site
-- row's (organization_id, id), so a cross-organization site reference is
-- impossible to store.

CREATE UNIQUE INDEX sites_org_id_idx ON sites (organization_id, id);

CREATE TABLE assets (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    site_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    name TEXT NOT NULL,
    criticality TEXT NOT NULL CHECK (criticality IN ('low','medium','high')),
    purchase_cost_cents INTEGER NOT NULL CHECK (purchase_cost_cents >= 0),
    version INTEGER NOT NULL CHECK (version > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    UNIQUE (organization_id, tag),
    FOREIGN KEY (organization_id, site_id) REFERENCES sites (organization_id, id)
);
