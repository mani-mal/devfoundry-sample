-- Migration 0014: labor entries storage (T029, M4).
-- One row per labor entry; the entry stores its hourly rate and computed
-- cost at write time (later rate changes never rewrite history). minutes
-- and rate are bounded positive integers; cost_cents is computed
-- server-side with integer round-half-up. The composite FK mirrors 0013.

CREATE TABLE labor_entries (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    work_order_id TEXT NOT NULL,
    technician_id TEXT NOT NULL,
    minutes INTEGER NOT NULL CHECK (minutes > 0),
    rate_cents_per_hour INTEGER NOT NULL CHECK (rate_cents_per_hour > 0),
    cost_cents INTEGER NOT NULL CHECK (cost_cents >= 0),
    note TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (organization_id, work_order_id) REFERENCES work_orders (organization_id, id)
);

CREATE INDEX labor_entries_wo_idx
    ON labor_entries (organization_id, work_order_id);
