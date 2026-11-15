-- Migration 0019: idempotency record core storage (T037, M5).
-- Scope per spec 7.3: organization + actor + operation + key. The
-- canonical request digest is stored at begin time; the same key with
-- the same digest replays the original record, the same key with a
-- different digest is a conflict (409). Concurrent repeats produce one
-- business effect (the UNIQUE constraint admits exactly one row per
-- scope). Bounded retention lands with sessions retention later.

CREATE TABLE idempotency_records (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    actor_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    key TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'completed', 'failed')),
    result_payload TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (organization_id, actor_id, operation, key)
);

CREATE INDEX idempotency_records_org_idx
    ON idempotency_records (organization_id);
