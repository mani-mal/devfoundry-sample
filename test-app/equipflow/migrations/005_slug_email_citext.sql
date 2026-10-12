-- Additive only: case-insensitive uniqueness for org slugs and user emails.
-- Pre-existing case-variant duplicates are collapsed before the unique indexes
-- are built so the migration cannot fail on dirty data.

DELETE FROM users u
  USING users d
  WHERE u.id <> d.id
    AND LOWER(u.email) = LOWER(d.email)
    AND LOWER(u.email) IN (SELECT LOWER(email) FROM users GROUP BY LOWER(email) HAVING COUNT(*) > 1)
    AND u.created_at > d.created_at;

DELETE FROM orgs o
  USING orgs d
  WHERE o.id <> d.id
    AND LOWER(o.slug) = LOWER(d.slug)
    AND LOWER(o.slug) IN (SELECT LOWER(slug) FROM orgs GROUP BY LOWER(slug) HAVING COUNT(*) > 1)
    AND o.created_at > d.created_at;

DELETE FROM users WHERE org_id IN (SELECT id FROM orgs o WHERE NOT EXISTS (SELECT 1 FROM orgs d WHERE d.id = o.id));

CREATE UNIQUE INDEX IF NOT EXISTS idx_orgs_slug_lower ON orgs (LOWER(slug));

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_lower ON users (LOWER(email));
