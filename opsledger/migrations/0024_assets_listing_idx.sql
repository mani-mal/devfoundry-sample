-- Migration 0024: assets listing index (T068, M9).
-- A covering index on (organization_id, created_at, id) lets the asset
-- listing serve its WHERE organization_id = ? ... ORDER BY created_at ASC,
-- id ASC ... LIMIT ? query from the index: the TEMP B-TREE sort disappears
-- and the plan becomes a covering-index search. Results are identical --
-- the index columns are the listing's full order key.

CREATE INDEX idx_assets_org_created ON assets (organization_id, created_at, id);
