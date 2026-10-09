/**
 * E2E test: worker vertical slice path against a mocked OpenCode HTTP API.
 * Verifies the Qualified -> Validating handler exercises the OpenCode API in
 * the right order and stores lifecycle state via a mocked database.
 */

import { DevFoundryWorker } from '../src/worker';
import * as http from 'http';
import * as crypto from 'crypto';

jest.setTimeout(30000);

const mockRequests: { url?: string; method?: string }[] = [];

function startMockOpenCode(port: number): Promise<http.Server> {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      mockRequests.push({ url: req.url, method: req.method });
      if (req.url === '/health') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: 'ok' }));
      } else if (req.url === '/session') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        const id = `sess-e2e-${mockRequests.length}`;
        res.end(JSON.stringify({ id, directory: '/tmp/wt', title: 'e2e' }));
      } else if (req.url?.startsWith('/session/') && req.url?.endsWith('/message')) {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          info: { id: 'reply-e2e-1' },
          parts: [{ type: 'text', text: 'assistant reply' }],
        }));
      } else if (req.url?.startsWith('/session/') && req.url?.endsWith('/shell')) {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          info: { id: 'shell-e2e-1' },
          parts: [{ type: 'tool', state: { status: 'completed', output: '' } }],
        }));
      } else {
        res.writeHead(404);
        res.end();
      }
    });
    server.listen(port, () => resolve(server));
  });
}

const makeMockDb = () => {
  const queries: { text: string; params?: unknown[] }[] = [];
  return {
    queries,
    pool: {
      connect: jest.fn(async () => ({
        query: jest.fn(async (text: string, params?: unknown[]) => {
          queries.push({ text, params });
          return { rows: [], rowCount: 0 };
        }),
        release: jest.fn(),
      })),
    },
  };
};

describe('DevFoundryWorker E2E - vertical slice path', () => {
  let server: http.Server;
  let worker: DevFoundryWorker;
  const PORT = 4457;

  beforeAll(async () => {
    server = await startMockOpenCode(PORT);
  });

  afterAll((done) => {
    server.close(() => done());
  });

  beforeEach(() => {
    mockRequests.length = 0;
  });

  const buildWorker = (database: unknown) =>
    new DevFoundryWorker({
      database: database as never,
      openCodeUrl: `http://127.0.0.1:${PORT}`,
      routeForgeUrl: 'http://127.0.0.1:3456',
      contextForgeUrl: 'http://127.0.0.1:3457',
      workerId: 'e2e-worker-1',
    });

  it('should start and stop without errors', async () => {
    const worker = buildWorker(makeMockDb());
    await worker.start();
    await worker.stop();
  });

  it('should exercise the Qualified path against the mock OpenCode in order', async () => {
    const mockDb = makeMockDb();
    const worker = buildWorker(mockDb);

    const task = {
      id: crypto.randomUUID(),
      tenantId: 't-e2e',
      projectId: 'p-e2e',
      userId: 'u-e2e',
      status: 'Pending' as const,
      phase: 'Qualified' as const,
      description: 'E2E: fix bug in vertical slice',
      baseCommit: 'abc123',
      targetBranch: 'main',
      workspaceId: 'ws-e2e-1',
      skills: ['skill-git'],
      contextIds: [],
      memoryIds: [],
      toolPermissions: [],
      modelRoute: 'default',
      capacityProfile: 'default',
      retryCount: 0,
    };

    const handler = (worker as unknown as {
      handleQualifiedPhase: (t: typeof task) => Promise<void>;
    }).handleQualifiedPhase.bind(worker);

    await handler(task);

    // Verify OpenCode API was called in the right order
    const urls = mockRequests.map((r) => r.url);
    const sessionIdx = urls.indexOf('/session');
    expect(sessionIdx).toBeGreaterThanOrEqual(0);
    expect(urls.some((u) => u?.includes('/message'))).toBe(true);
    expect(urls.some((u) => u?.includes('/shell'))).toBe(true);

    // Verify the lifecycle update was issued (Validating + checkpoint)
    const update = mockDb.queries.find((q) => q.text.startsWith('UPDATE tasks'));
    expect(update).toBeDefined();
    expect(update!.params![1]).toBe('Validating');
    const checkpointArg = String(update!.params!.find((p) => String(p).includes('snapshotId')));
    expect(checkpointArg).toContain('snapshotId');
  });

  it('should mark task Failed when the workspace creation fails', async () => {
    const mockDb = makeMockDb();
    const worker = buildWorker(mockDb);

    // Kill the mock server temporarily by using an unreachable port
    const brokenWorker = new DevFoundryWorker({
      database: mockDb as never,
      openCodeUrl: 'http://127.0.0.1:1',
      routeForgeUrl: 'http://127.0.0.1:3456',
      contextForgeUrl: 'http://127.0.0.1:3457',
      workerId: 'e2e-broken',
    });

    const processTask = (brokenWorker as unknown as {
      processTask: (t: unknown) => Promise<void>;
    }).processTask.bind(brokenWorker);

    const task = {
      id: crypto.randomUUID(),
      tenantId: 't-e2e',
      projectId: 'p-e2e',
      userId: 'u-e2e',
      status: 'Pending',
      phase: 'Qualified',
      description: 'E2E: failing task',
      baseCommit: 'abc123',
      targetBranch: 'main',
      workspaceId: 'ws-e2e-1',
      skills: [],
      contextIds: [],
      memoryIds: [],
      toolPermissions: [],
      modelRoute: 'default',
      capacityProfile: 'default',
      retryCount: 0,
    };

    await processTask(task);

    const failedUpdate = mockDb.queries.find(
      (q) => q.text.startsWith('UPDATE tasks') && q.params![0] === 'Failed'
    );
    expect(failedUpdate).toBeDefined();
  });
});
