-- Migration 0015: work-order comments storage (T030, M4).
-- One row per comment; the body is stored VERBATIM (user text is literal,
-- never interpreted or transformed) and every comment anchors to the work
-- order's aggregate version at write time (version-aware history). The
-- composite FK mirrors 0014.

CREATE TABLE comments (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    work_order_id TEXT NOT NULL,
    author_id TEXT NOT NULL,
    body TEXT NOT NULL,
    at_version INTEGER NOT NULL CHECK (at_version > 0),
    created_at TEXT NOT NULL,
    FOREIGN KEY (organization_id, work_order_id) REFERENCES work_orders (organization_id, id)
);

CREATE INDEX comments_wo_idx
    ON comments (organization_id, work_order_id);
