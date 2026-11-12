CREATE TABLE csrf_contexts (
    token_hash TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    rotated_at TEXT
);
