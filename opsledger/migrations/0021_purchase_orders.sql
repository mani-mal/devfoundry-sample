-- Migration 0021: purchase order and receipt storage (T044, T045, M6).
-- One order issued from one approved request; order lines mirror the
-- request lines at issue time (integer cents; later request edits never
-- rewrite an order). Receipts are partial: a receipt row plus its lines
-- record what arrived; the outstanding quantity is the ordered quantity
-- minus the received sum and can never fall below zero (over-receipt is
-- rejected). A receipt writes its rows, the stock movements, the
-- balance updates, the audit records, and the idempotency completion in
-- ONE transaction (spec 7.5). Replay with the same key adds nothing.

CREATE TABLE purchase_orders (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    purchase_request_id TEXT NOT NULL,
    vendor_id TEXT NOT NULL,
    issued_by TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'received', 'cancelled')),
    total_cents INTEGER NOT NULL CHECK (total_cents >= 0),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    FOREIGN KEY (organization_id, purchase_request_id) REFERENCES purchase_requests (organization_id, id),
    FOREIGN KEY (organization_id, vendor_id) REFERENCES vendors (organization_id, id)
);

CREATE TABLE purchase_order_lines (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    purchase_order_id TEXT NOT NULL,
    part_id TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_cost_cents INTEGER NOT NULL CHECK (unit_cost_cents >= 0),
    created_at TEXT NOT NULL,
    FOREIGN KEY (organization_id, purchase_order_id) REFERENCES purchase_orders (organization_id, id),
    FOREIGN KEY (organization_id, part_id) REFERENCES parts (organization_id, id)
);

CREATE TABLE receipts (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    purchase_order_id TEXT NOT NULL,
    stock_location_id TEXT NOT NULL,
    received_by TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('received', 'voided')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (organization_id, purchase_order_id) REFERENCES purchase_orders (organization_id, id),
    FOREIGN KEY (organization_id, stock_location_id) REFERENCES stock_locations (organization_id, id)
);

CREATE TABLE receipt_lines (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    receipt_id TEXT NOT NULL,
    part_id TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_cost_cents INTEGER NOT NULL CHECK (unit_cost_cents >= 0),
    created_at TEXT NOT NULL,
    archived_at TEXT,
    FOREIGN KEY (organization_id, receipt_id) REFERENCES receipts (organization_id, id),
    FOREIGN KEY (organization_id, part_id) REFERENCES parts (organization_id, id)
);

CREATE UNIQUE INDEX purchase_orders_org_id_idx
    ON purchase_orders (organization_id, id);

CREATE UNIQUE INDEX purchase_order_lines_org_id_idx
    ON purchase_order_lines (organization_id, id);

CREATE UNIQUE INDEX receipts_org_id_idx ON receipts (organization_id, id);

CREATE UNIQUE INDEX receipt_lines_org_id_idx
    ON receipt_lines (organization_id, id);

CREATE INDEX purchase_orders_request_idx
    ON purchase_orders (organization_id, purchase_request_id);

CREATE INDEX purchase_order_lines_order_idx
    ON purchase_order_lines (organization_id, purchase_order_id);

CREATE INDEX receipts_order_idx ON receipts (organization_id, purchase_order_id);

CREATE INDEX receipt_lines_receipt_idx
    ON receipt_lines (organization_id, receipt_id);

CREATE INDEX purchase_orders_org_idx ON purchase_orders (organization_id);

CREATE INDEX receipts_org_idx ON receipts (organization_id);
