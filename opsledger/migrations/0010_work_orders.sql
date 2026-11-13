-- Migration 0010: work orders storage (T025, M4).
-- The composite foreign keys make cross-organization site/asset references
-- impossible to store (same mechanism as 0008).

CREATE UNIQUE INDEX assets_org_id_idx ON assets (organization_id, id);

CREATE TABLE work_orders (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    site_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    number TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    priority TEXT NOT NULL CHECK (priority IN ('low','medium','high')),
    status TEXT NOT NULL CHECK (status IN ('open','assigned','in_progress','blocked','completed','closed','cancelled')),
    requester_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    UNIQUE (organization_id, number),
    FOREIGN KEY (organization_id, site_id) REFERENCES sites (organization_id, id),
    FOREIGN KEY (organization_id, asset_id) REFERENCES assets (organization_id, id)
);
