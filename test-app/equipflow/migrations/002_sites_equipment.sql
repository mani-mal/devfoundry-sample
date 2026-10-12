CREATE TABLE IF NOT EXISTS customer_sites (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES orgs(id),
  name TEXT NOT NULL,
  address TEXT NOT NULL,
  city TEXT NOT NULL,
  region TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_customer_sites_org ON customer_sites(org_id);

CREATE TABLE IF NOT EXISTS equipment (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES orgs(id),
  site_id UUID NOT NULL REFERENCES customer_sites(id),
  name TEXT NOT NULL,
  serial TEXT NOT NULL,
  model TEXT,
  installed_at TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'operational' CHECK (status IN ('operational','degraded','down','retired')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (org_id, serial)
);

CREATE INDEX IF NOT EXISTS idx_equipment_org ON equipment(org_id);
CREATE INDEX IF NOT EXISTS idx_equipment_site ON equipment(site_id);
