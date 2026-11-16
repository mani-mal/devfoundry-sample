-- Migration 0022: maintenance plan and run storage (T049, T051, M7).
-- UTC date-based maintenance plans: a plan pins a positive day interval
-- and a bounded preview/generation horizon. maintenance_runs is the
-- persisted generation state: the UNIQUE (organization_id, plan_id,
-- scheduled_date) key admits exactly one run per plan and scheduled
-- date, so idempotent generation -- including concurrent runs and a
-- simulated crash/retry -- creates one work order per plan/date.
-- attempt_count, next_retry_at, and last_error carry the bounded retry.

CREATE TABLE maintenance_plans (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    site_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    interval_days INTEGER NOT NULL CHECK (interval_days > 0),
    horizon_days INTEGER NOT NULL CHECK (horizon_days > 0 AND horizon_days <= 366),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    version INTEGER NOT NULL CHECK (version > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    FOREIGN KEY (organization_id, site_id) REFERENCES sites (organization_id, id),
    FOREIGN KEY (organization_id, asset_id) REFERENCES assets (organization_id, id)
);

CREATE UNIQUE INDEX maintenance_plans_org_id_idx
    ON maintenance_plans (organization_id, id);

CREATE TABLE maintenance_runs (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    plan_id TEXT NOT NULL,
    scheduled_date TEXT NOT NULL,
    work_order_id TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'generated', 'failed', 'skipped')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_error TEXT,
    next_retry_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (organization_id, plan_id, scheduled_date),
    FOREIGN KEY (organization_id, plan_id) REFERENCES maintenance_plans (organization_id, id)
);

CREATE UNIQUE INDEX maintenance_runs_org_id_idx
    ON maintenance_runs (organization_id, id);

CREATE INDEX maintenance_runs_due_idx
    ON maintenance_runs (organization_id, status, next_retry_at);

CREATE INDEX maintenance_plans_org_idx ON maintenance_plans (organization_id);

CREATE INDEX maintenance_runs_org_idx ON maintenance_runs (organization_id);
