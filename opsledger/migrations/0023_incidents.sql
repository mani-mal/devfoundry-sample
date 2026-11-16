-- Migration 0023: incident storage (T053, T054, M7).
-- Incidents and their corrective actions, plus the incident/work-order
-- link. Composite FKs mirror 0010: a link cannot reference an incident
-- or a work order from another organization, and the link service
-- checks that both share the same site. Corrective actions carry a
-- required flag: an incident cannot close while a required action is
-- open. No safety certification claims anywhere.

CREATE TABLE incidents (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    site_id TEXT NOT NULL,
    asset_id TEXT,
    reported_by TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    status TEXT NOT NULL CHECK (status IN ('open', 'investigating', 'closed')),
    occurred_at TEXT,
    closed_at TEXT,
    version INTEGER NOT NULL CHECK (version > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (organization_id, site_id) REFERENCES sites (organization_id, id),
    FOREIGN KEY (organization_id, asset_id) REFERENCES assets (organization_id, id)
);

CREATE UNIQUE INDEX incidents_org_id_idx ON incidents (organization_id, id);

CREATE TABLE corrective_actions (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    incident_id TEXT NOT NULL,
    title TEXT NOT NULL,
    instructions TEXT NOT NULL,
    required INTEGER NOT NULL CHECK (required IN (0, 1)),
    status TEXT NOT NULL CHECK (status IN ('open', 'in_progress', 'done', 'cancelled')),
    assigned_to TEXT,
    due_date TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (organization_id, incident_id) REFERENCES incidents (organization_id, id)
);

CREATE UNIQUE INDEX corrective_actions_org_id_idx
    ON corrective_actions (organization_id, id);

CREATE TABLE incident_work_orders (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    incident_id TEXT NOT NULL,
    work_order_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (organization_id, incident_id, work_order_id),
    FOREIGN KEY (organization_id, incident_id) REFERENCES incidents (organization_id, id),
    FOREIGN KEY (organization_id, work_order_id) REFERENCES work_orders (organization_id, id)
);

CREATE INDEX incidents_org_idx ON incidents (organization_id);

CREATE INDEX corrective_actions_incident_idx
    ON corrective_actions (organization_id, incident_id);

CREATE INDEX incident_work_orders_incident_idx
    ON incident_work_orders (organization_id, incident_id);
