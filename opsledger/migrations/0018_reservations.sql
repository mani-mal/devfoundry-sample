-- Migration 0018: reservation storage (T035, M5).
-- One row per reservation; remaining_quantity tracks release/consume
-- (quantities cannot be reused or exceed the reservation). status is
-- active/released/consumed. Composite FKs mirror 0017; work_order_id
-- carries the composite FK into work_orders.

CREATE TABLE reservations (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    part_id TEXT NOT NULL,
    stock_location_id TEXT NOT NULL,
    work_order_id TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    remaining_quantity INTEGER NOT NULL CHECK (remaining_quantity >= 0),
    status TEXT NOT NULL CHECK (status IN ('active', 'released', 'consumed')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    released_at TEXT,
    FOREIGN KEY (organization_id, part_id) REFERENCES parts (organization_id, id),
    FOREIGN KEY (organization_id, stock_location_id) REFERENCES stock_locations (organization_id, id),
    FOREIGN KEY (organization_id, work_order_id) REFERENCES work_orders (organization_id, id)
);

CREATE INDEX reservations_work_order_idx
    ON reservations (organization_id, work_order_id);

CREATE INDEX reservations_part_loc_idx
    ON reservations (organization_id, part_id, stock_location_id);
