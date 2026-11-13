CREATE TABLE site_memberships (
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    site_id TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES users(id),
    granted_at TEXT NOT NULL,
    revoked_at TEXT,
    PRIMARY KEY (organization_id, site_id, user_id)
);
