import { Pool, Client } from 'pg';
import { readFileSync, readdirSync } from 'fs';
import { join } from 'path';

const testDbUrl = 'postgresql://equipflow:equipflow@localhost:5433/equipflow_test';

const testDbName = testDbUrl.split('/').pop() as string;
const maintenanceUrl = testDbUrl.replace(/\/[^/]+$/, '/equipflow');

process.env.DATABASE_URL = testDbUrl;

export default async function globalSetup(): Promise<void> {
  const maintenance = new Client({ connectionString: maintenanceUrl });
  await maintenance.connect();
  try {
    await maintenance.query(`CREATE DATABASE ${testDbName}`);
  } catch (err) {
    if ((err as { code?: string }).code !== '42P04') {
      throw err;
    }
  } finally {
    await maintenance.end();
  }

  const pool = new Pool({ connectionString: testDbUrl });
  try {
    await pool.query(
      'DROP TABLE IF EXISTS customer_sites, equipment, users, orgs, schema_migrations CASCADE'
    );
    const migrationsDir = join(__dirname, '..', 'migrations');
    const files = readdirSync(migrationsDir)
      .filter((f) => f.endsWith('.sql'))
      .sort();
    for (const file of files) {
      const sql = readFileSync(join(migrationsDir, file), 'utf8');
      await pool.query(sql);
    }
  } finally {
    await pool.end();
  }
}
