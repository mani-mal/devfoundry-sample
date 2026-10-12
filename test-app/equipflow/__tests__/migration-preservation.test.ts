import { Client } from 'pg';
import { readFileSync } from 'fs';
import { join } from 'path';
import bcrypt from 'bcryptjs';

const PRESERVATION_URL =
  process.env.TEST_DATABASE_URL ||
  'postgresql://equipflow:equipflow@localhost:5433/equipflow_preservation';

const preservationDb = PRESERVATION_URL.split('/').pop() as string;
const maintenanceUrl = PRESERVATION_URL.replace(/\/[^/]+$/, '/equipflow');

const migrationsDir = join(__dirname, '..', 'migrations');

interface OrgSnapshot {
  id: string;
  name: string;
  slug: string;
}

interface UserSnapshot {
  id: string;
  org_id: string;
  email: string;
  name: string;
  role: string;
  password_hash: string;
}

interface Snapshot {
  orgs: OrgSnapshot[];
  users: UserSnapshot[];
}

let client: Client;
let snapshot: Snapshot;

async function applyMigrationFile(
  filename: string,
  recordInSchemaMigrations: boolean
): Promise<void> {
  const sql = readFileSync(join(migrationsDir, filename), 'utf8');
  await client.query('BEGIN');
  if (recordInSchemaMigrations) {
    await client.query(
      'INSERT INTO schema_migrations (filename) VALUES ($1)',
      [filename]
    );
  }
  await client.query(sql);
  await client.query('COMMIT');
}

async function countRows(table: string): Promise<number> {
  const res = await client.query<{ count: string }>(
    `SELECT COUNT(*)::text AS count FROM ${table}`
  );
  return parseInt(res.rows[0].count, 10);
}

async function tableExists(table: string): Promise<boolean> {
  const res = await client.query(
    `SELECT 1 FROM information_schema.tables
     WHERE table_schema = 'public' AND table_name = $1`,
    [table]
  );
  return res.rowCount === 1;
}

async function columnExists(
  table: string,
  column: string
): Promise<boolean> {
  const res = await client.query(
    `SELECT 1 FROM information_schema.columns
     WHERE table_schema = 'public' AND table_name = $1 AND column_name = $2`,
    [table, column]
  );
  return res.rowCount === 1;
}

beforeAll(async () => {
  const maintenance = new Client({ connectionString: maintenanceUrl });
  await maintenance.connect();
  try {
    await maintenance.query(`CREATE DATABASE ${preservationDb}`);
  } catch (err) {
    if ((err as { code?: string }).code !== '42P04') {
      throw err;
    }
  } finally {
    await maintenance.end();
  }

  client = new Client({ connectionString: PRESERVATION_URL });
  await client.connect();

  await client.query(
    `DROP TABLE IF EXISTS schema_migrations, work_orders, service_requests,
     equipment, customer_sites, users, orgs CASCADE`
  );

  const migration001 = readFileSync(
    join(migrationsDir, '001_orgs_users.sql'),
    'utf8'
  );
  await client.query('CREATE TABLE IF NOT EXISTS schema_migrations (filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT NOW())');
  await client.query(migration001);

  const orgARes = await client.query<OrgSnapshot>(
    "INSERT INTO orgs (name, slug) VALUES ('Org A', 'org-a') RETURNING id, name, slug"
  );
  const orgBRes = await client.query<OrgSnapshot>(
    "INSERT INTO orgs (name, slug) VALUES ('Org B', 'org-b') RETURNING id, name, slug"
  );
  const orgA = orgARes.rows[0];
  const orgB = orgBRes.rows[0];

  const adminHash = bcrypt.hashSync('admin-password', 10);
  const techHash = bcrypt.hashSync('tech-password', 10);
  const userBHash = bcrypt.hashSync('userb-password', 10);

  const adminRes = await client.query<UserSnapshot>(
    "INSERT INTO users (org_id, email, name, role, password_hash) VALUES ($1, 'admin@org-a.test', 'Alice Admin', 'admin', $2) RETURNING id, org_id, email, name, role, password_hash",
    [orgA.id, adminHash]
  );
  const techRes = await client.query<UserSnapshot>(
    "INSERT INTO users (org_id, email, name, role, password_hash) VALUES ($1, 'tech@org-a.test', 'Bob Tech', 'technician', $2) RETURNING id, org_id, email, name, role, password_hash",
    [orgA.id, techHash]
  );
  const userBRes = await client.query<UserSnapshot>(
    "INSERT INTO users (org_id, email, name, role, password_hash) VALUES ($1, 'manager@org-b.test', 'Carol Manager', 'manager', $2) RETURNING id, org_id, email, name, role, password_hash",
    [orgB.id, userBHash]
  );

  snapshot = {
    orgs: [orgA, orgB],
    users: [adminRes.rows[0], techRes.rows[0], userBRes.rows[0]],
  };

  await applyMigrationFile('002_sites_equipment.sql', true);
  await applyMigrationFile('003_service_requests.sql', true);
  await applyMigrationFile('004_work_orders.sql', true);
});

afterAll(async () => {
  if (client) {
    await client.end();
  }
});

describe('migration preservation (001 seed → 002/003/004 apply)', () => {
  test('orgs are preserved: same count, same ids, same names/slugs', async () => {
    expect(await countRows('orgs')).toBe(snapshot.orgs.length);
    const res = await client.query<OrgSnapshot>(
      'SELECT id, name, slug FROM orgs ORDER BY id'
    );
    const expected = [...snapshot.orgs].sort((a, b) =>
      a.id.localeCompare(b.id)
    );
    expect(res.rows).toEqual(expected);
  });

  test('users are preserved: same count, ids, org mapping, emails, names, roles', async () => {
    expect(await countRows('users')).toBe(snapshot.users.length);
    const res = await client.query<UserSnapshot>(
      'SELECT id, org_id, email, name, role, password_hash FROM users ORDER BY id'
    );
    const expected = [...snapshot.users].sort((a, b) =>
      a.id.localeCompare(b.id)
    );
    expect(res.rows).toEqual(expected);
  });

  test('password hashes are byte-identical to the seed', async () => {
    const res = await client.query<{ id: string; password_hash: string }>(
      'SELECT id, password_hash FROM users'
    );
    const seeded = new Map(snapshot.users.map((u) => [u.id, u.password_hash]));
    expect(res.rows.length).toBe(seeded.size);
    for (const row of res.rows) {
      expect(row.password_hash).toBe(seeded.get(row.id));
    }
  });

  test('new tables added by 002/003/004 exist', async () => {
    expect(await tableExists('customer_sites')).toBe(true);
    expect(await tableExists('equipment')).toBe(true);
    expect(await tableExists('service_requests')).toBe(true);
    expect(await tableExists('work_orders')).toBe(true);
  });

  test('key columns exist on new tables (equipment.serial, work_orders.code)', async () => {
    expect(await columnExists('equipment', 'serial')).toBe(true);
    expect(await columnExists('work_orders', 'code')).toBe(true);
    expect(await columnExists('work_orders', 'assigned_technician_id')).toBe(
      true
    );
    expect(await columnExists('service_requests', 'equipment_id')).toBe(true);
  });

  test('schema_migrations records the applied migration files', async () => {
    const res = await client.query<{ filename: string }>(
      'SELECT filename FROM schema_migrations ORDER BY filename'
    );
    expect(res.rows.map((r) => r.filename)).toEqual([
      '002_sites_equipment.sql',
      '003_service_requests.sql',
      '004_work_orders.sql',
    ]);
  });

  test('seed data still JOINs with new tables: post-migration customer_site resolves org A admin', async () => {
    const orgA = snapshot.orgs.find((o) => o.slug === 'org-a') as OrgSnapshot;
    const admin = snapshot.users.find(
      (u) => u.email === 'admin@org-a.test'
    ) as UserSnapshot;

    const siteRes = await client.query<{ id: string }>(
      "INSERT INTO customer_sites (org_id, name, address, city) VALUES ($1, 'Alpha HQ', '1 Alpha Way', 'Springfield') RETURNING id",
      [orgA.id]
    );
    const siteId = siteRes.rows[0].id;

    const equipmentRes = await client.query<{ id: string }>(
      "INSERT INTO equipment (org_id, site_id, name, serial) VALUES ($1, $2, 'Alpha Pump', 'AP-0001') RETURNING id",
      [orgA.id, siteId]
    );
    const equipmentId = equipmentRes.rows[0].id;

    const woRes = await client.query<{ id: string }>(
      "INSERT INTO work_orders (org_id, code, title, site_id, equipment_id) VALUES ($1, 'WO-2026-0001', 'Inspect pump', $2, $3) RETURNING id",
      [orgA.id, siteId, equipmentId]
    );
    expect(woRes.rows[0].id).toBeDefined();

    const joinRes = await client.query<{ email: string; org_slug: string }>(
      `SELECT u.email, o.slug AS org_slug
       FROM work_orders wo
       JOIN customer_sites cs ON cs.id = wo.site_id
       JOIN orgs o ON o.id = cs.org_id
       JOIN users u ON u.org_id = o.id
       WHERE wo.code = 'WO-2026-0001' AND u.role = 'admin'`
    );
    expect(joinRes.rows).toEqual([
      { email: admin.email, org_slug: 'org-a' },
    ]);
  });
});
