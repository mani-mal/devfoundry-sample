-- Migration 0020: purchase request storage (T041, M6).
-- Vendors and purchase requests with lines and approvals. Request
-- totals are integer cents: each line stores its own unit cost and the
-- request stores the server-computed total (the sum of quantity times
-- unit_cost_cents). Composite FKs mirror 0017: a line cannot reference
-- a part or a request from another organization, and a request cannot
-- reference another organization's vendor. Approvals record the total
-- they approved; invalidated_at stamps approvals that a later material
-- edit invalidated (T043) — an approved total is never silently
-- changed. The requester cannot approve their own request (service
-- check, T042).

CREATE TABLE vendors (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    name TEXT NOT NULL,
    contact_email TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    UNIQUE (organization_id, name)
);

CREATE TABLE purchase_requests (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    vendor_id TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'submitted', 'approved', 'rejected', 'cancelled', 'ordered')),
    total_cents INTEGER NOT NULL DEFAULT 0 CHECK (total_cents >= 0),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    FOREIGN KEY (organization_id, vendor_id) REFERENCES vendors (organization_id, id)
);

CREATE TABLE purchase_request_lines (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    purchase_request_id TEXT NOT NULL,
    part_id TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_cost_cents INTEGER NOT NULL CHECK (unit_cost_cents >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    FOREIGN KEY (organization_id, purchase_request_id) REFERENCES purchase_requests (organization_id, id),
    FOREIGN KEY (organization_id, part_id) REFERENCES parts (organization_id, id)
);

CREATE TABLE approvals (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    purchase_request_id TEXT NOT NULL,
    approver_id TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
    approved_total_cents INTEGER NOT NULL CHECK (approved_total_cents >= 0),
    reason TEXT,
    decided_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    invalidated_at TEXT,
    FOREIGN KEY (organization_id, purchase_request_id) REFERENCES purchase_requests (organization_id, id)
);

CREATE UNIQUE INDEX vendors_org_id_idx ON vendors (organization_id, id);

CREATE UNIQUE INDEX purchase_requests_org_id_idx
    ON purchase_requests (organization_id, id);

CREATE UNIQUE INDEX purchase_request_lines_org_id_idx
    ON purchase_request_lines (organization_id, id);

CREATE INDEX purchase_requests_vendor_idx
    ON purchase_requests (organization_id, vendor_id);

CREATE INDEX purchase_request_lines_request_idx
    ON purchase_request_lines (organization_id, purchase_request_id);

CREATE INDEX approvals_request_idx
    ON approvals (organization_id, purchase_request_id);

CREATE INDEX vendors_org_idx ON vendors (organization_id);

CREATE INDEX purchase_requests_org_idx ON purchase_requests (organization_id);
