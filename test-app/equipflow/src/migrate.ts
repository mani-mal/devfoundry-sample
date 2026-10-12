import { readFileSync, readdirSync } from 'fs';
import { join } from 'path';
import { pool } from './db';

interface PgError extends Error {
  code?: string;
}

const MIGRATIONS_DIR = join(__dirname, '..', 'migrations');

async function ensureMigrationsTable(): Promise<void> {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS schema_migrations (
      filename TEXT PRIMARY KEY,
      applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
  `);
}

async function getApplied(): Promise<Set<string>> {
  const result = await pool.query<{ filename: string }>(
    'SELECT filename FROM schema_migrations'
  );
  return new Set(result.rows.map((row) => row.filename));
}

async function applyMigration(filename: string, sql: string): Promise<void> {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    await client.query(sql);
    await client.query('INSERT INTO schema_migrations (filename) VALUES ($1)', [
      filename,
    ]);
    await client.query('COMMIT');
    console.log(`applied migration: ${filename}`);
  } catch (err) {
    await client.query('ROLLBACK');
    throw err;
  } finally {
    client.release();
  }
}

async function main(): Promise<void> {
  await ensureMigrationsTable();
  const applied = await getApplied();
  const files = readdirSync(MIGRATIONS_DIR)
    .filter((file) => file.endsWith('.sql'))
    .sort();

  for (const filename of files) {
    if (applied.has(filename)) {
      console.log(`skipping migration: ${filename} (already applied)`);
      continue;
    }
    const sql = readFileSync(join(MIGRATIONS_DIR, filename), 'utf-8');
    await applyMigration(filename, sql);
  }

  await pool.end();
}

main().catch((err: PgError) => {
  console.error('migration failed:', err.message);
  process.exit(1);
});
