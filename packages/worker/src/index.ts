import { DevFoundryWorker } from './worker';
import { DevFoundryCore } from '@dev-foundry/core';

const WORKER_ID = process.env.WORKER_ID || 'worker-1';

const coreOptions = {
  databaseUrl: process.env.DATABASE_URL || 'postgres://devfoundry:devfoundry@localhost:5432/devfoundry',
  routeForgeUrl: process.env.ROUTEFORGE_URL || 'http://localhost:8000',
};

const core = new DevFoundryCore(coreOptions);

const workerOptions = {
  core,
  workerId: WORKER_ID,
};

const worker = new DevFoundryWorker(workerOptions);

async function main(): Promise<void> {
  await core.connect();
  await worker.start();

  process.on('SIGTERM', async () => {
    await worker.stop();
    await core.disconnect();
    process.exit(0);
  });

  process.on('SIGINT', async () => {
    await worker.stop();
    await core.disconnect();
    process.exit(0);
  });
}

main().catch((error) => {
  console.error('Failed to start worker', error);
  process.exit(1);
});
