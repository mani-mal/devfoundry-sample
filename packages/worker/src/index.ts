import { Database } from '@dev-foundry/core';
import { DevFoundryWorker } from './worker';

export { DevFoundryWorker } from './worker';
export * from './worker';

if (require.main === module) {
  const databaseUrl =
    process.env.DATABASE_URL ||
    'postgresql://devfoundry:devfoundry@postgres:5432/devfoundry';

  const dbUrlMatch = databaseUrl.match(/postgres(?:ql)?:\/\/([^:]+):([^@]+)@([^:]+):(\d+)\/(.+)/);
  if (!dbUrlMatch) {
    console.error('[worker] Invalid DATABASE_URL');
    process.exit(1);
  }

  const [, username, password, host, port, dbName] = dbUrlMatch;
  const database = new Database({
    host,
    port: parseInt(port, 10),
    database: dbName,
    username,
    password,
  });

  const worker = new DevFoundryWorker({
    database,
    openCodeUrl: process.env.OPENCODE_URL || 'http://opencode:4096',
    routeForgeUrl: process.env.ROUTEFORGE_URL || 'http://routeforge:8000',
    contextForgeUrl: process.env.CONTEXFORGE_URL || 'http://contextforge:4444',
    workerId: process.env.WORKER_ID || 'worker-1',
  });

  const shutdown = async () => {
    await worker.stop();
    try { await database.close(); } catch { /* ignore */ }
    process.exit(0);
  };
  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);

  worker.start().catch((err) => {
    console.error('[worker] Failed to start:', err instanceof Error ? err.message : err);
    process.exit(1);
  });

  // keep the event loop alive
  setInterval(() => {}, 1 << 30);
}
