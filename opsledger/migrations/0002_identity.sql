-- Identity schema (T004): organizations, users, memberships.
-- Normalization rule: organization slugs and user emails are stored
-- lowercase-trimmed and unique. The CHECK constraints below reject any
-- value that is not already in its normalized form, so duplicate or
-- different-case values collide on the stored normalized value (UNIQUE)
-- and are never stored raw.

CREATE TABLE organizations (
    id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE CHECK (slug = lower(trim(slug))),
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE CHECK (email = lower(trim(email))),
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE memberships (
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    role TEXT NOT NULL CHECK (role IN ('developer','lead','auditor','approver','purchasing')),
    created_at TEXT NOT NULL,
    PRIMARY KEY (organization_id, user_id)
)
