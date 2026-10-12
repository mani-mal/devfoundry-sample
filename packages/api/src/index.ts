import express, { Request, Response, NextFunction } from 'express';
import { Pool } from 'pg';
import { v4 as uuidv4 } from 'uuid';
import os from 'os';
import { ContextStore, MemoryStore, SkillStore, ToolRegistry } from '@dev-foundry/core';
import { RouteForgeAdminClient } from '@dev-foundry/integrations-routeforge';

export class ApiServer {
  private app: express.Express;
  private port: number;
  private pool: Pool;
  private startTime = Date.now();
  private contextStore: ContextStore;
  private memoryStore: MemoryStore;
  private skillStore: SkillStore;
  private toolRegistry: ToolRegistry;
  private adminClient: RouteForgeAdminClient | null = null;

  private getRouteForgeAdmin(): RouteForgeAdminClient {
    if (!this.adminClient) {
      this.adminClient = new RouteForgeAdminClient({
        baseUrl: process.env.ROUTEFORGE_URL || 'http://routeforge:8000',
        email: process.env.ROUTEFORGE_ADMIN_EMAIL || 'admin@routeforge.local',
        password: process.env.ROUTEFORGE_ADMIN_PASSWORD || 'changeme',
      });
    }
    return this.adminClient;
  }

  constructor(port: number = 3000, databaseUrl?: string) {
    this.app = express();
    this.port = port;
    this.pool = new Pool({
      connectionString:
        databaseUrl ||
        process.env.DATABASE_URL ||
        'postgresql://devfoundry:devfoundry@localhost:5432/devfoundry',
      max: 10,
      idleTimeoutMillis: 30000,
      connectionTimeoutMillis: 5000,
    });
    this.setupRoutes();
    const dbAdapter = {
      query: async <T extends Record<string, unknown> = Record<string, unknown>>(text: string, params?: unknown[]): Promise<T[]> => {
        const result = await this.pool.query(text, params as never[]);
        return result.rows as T[];
      },
    };
    this.contextStore = new ContextStore(dbAdapter as never);
    this.memoryStore = new MemoryStore(dbAdapter as never);
    this.skillStore = new SkillStore(dbAdapter as never);
    this.toolRegistry = new ToolRegistry(dbAdapter as never);
  }

  private async ensureSchema(): Promise<void> {
    await this.pool.query(`
      CREATE TABLE IF NOT EXISTS tasks (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL,
        project_id UUID NOT NULL,
        user_id UUID NOT NULL,
        status VARCHAR(20) NOT NULL,
        phase VARCHAR(20) NOT NULL,
        description TEXT NOT NULL,
        base_commit VARCHAR(64) NOT NULL,
        target_branch VARCHAR(255) NOT NULL,
        workspace_id UUID NOT NULL,
        skills JSONB NOT NULL,
        context_ids UUID[],
        memory_ids UUID[],
        tool_permissions JSONB NOT NULL,
        model_route VARCHAR(255) NOT NULL,
        capacity_profile VARCHAR(50) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        started_at TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,
        retry_count INTEGER NOT NULL DEFAULT 0,
        checkpoint JSONB,
        outcome JSONB
      );
      CREATE TABLE IF NOT EXISTS task_outcomes (
        id UUID PRIMARY KEY,
        task_id UUID NOT NULL REFERENCES tasks(id),
        attempt_id UUID NOT NULL,
        success BOOLEAN NOT NULL,
        reason TEXT,
        evidence JSONB NOT NULL,
        trace_references JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
      );
    `);
  }

  private async seedDefaults(): Promise<void> {
    const tenantId = '00000000-0000-0000-0000-000000000000';
    const aclId = '00000000-0000-0000-0000-000000000000';

    try {
      const existing = await this.skillStore.list({ limit: 1 });
      if (existing.length === 0) {
        const defaultSkills = [
          { name: 'repo-orientation', description: 'Orient a new repo: layout, build, test commands', path: 'skills/repo-orientation', version: '1.0.0' },
          { name: 'patch-generation', description: 'Generate isolated patches for bug fixes', path: 'skills/patch-generation', version: '1.0.0' },
          { name: 'regression-testing', description: 'Run regression evidence for a candidate patch', path: 'skills/regression-testing', version: '1.0.0' },
          { name: 'security-review', description: 'Static security review of a change', path: 'skills/security-review', version: '1.0.0' },
          { name: 'ci-repair', description: 'Diagnose and repair broken CI pipelines', path: 'skills/ci-repair', version: '1.0.0' },
          { name: 'run-lint', description: 'Run the repo lint suite and report failures', path: 'skills/run-lint', version: '1.0.0' },
          { name: 'doc-drift', description: 'Detect documentation drift vs code changes', path: 'skills/doc-drift', version: '1.0.0' },
        ];
        for (const s of defaultSkills) {
          await this.skillStore.install({
            ...s,
            gitRepository: 'local://defaults',
            gitCommit: 'HEAD',
            approvalStatus: 'approved',
            ownerId: aclId,
          });
        }
      }

      await this.toolRegistry.register({ name: 'repo-search', description: 'Search the indexed repository content', kind: 'search', enabled: true, scopes: ['repo:read'] });
      await this.toolRegistry.register({ name: 'ticket-search', description: 'Search customer ticket system (read-only)', kind: 'search', enabled: true, scopes: ['tickets:read'] });
      await this.toolRegistry.register({ name: 'doc-search', description: 'Search project documentation (read-only)', kind: 'search', enabled: true, scopes: ['docs:read'] });
      await this.toolRegistry.register({ name: 'ci-status', description: 'Read CI pipeline status (read-only)', kind: 'read', enabled: true, scopes: ['ci:read'] });
      await this.toolRegistry.register({ name: 'artifact-inspect', description: 'Inspect build artifacts (read-only)', kind: 'read', enabled: true, scopes: ['artifacts:read'] });
      await this.toolRegistry.register({ name: 'sandbox-build', description: 'Approved sandbox build execution', kind: 'execute', enabled: true, scopes: ['build:execute'] });
      await this.toolRegistry.register({ name: 'git-publish', description: 'Publish branch/PR within the configured repo only', kind: 'write', enabled: false, scopes: ['git:write'] });

      const nodeCount = await this.contextStore.listNodes(tenantId, { limit: 1 });
      if (nodeCount.length === 0) {
        const repoNode = await this.contextStore.createNode({ tenantId, aclId, kind: 'repo', sourceId: 'devfoundry', revision: 'HEAD', metadata: { name: 'devfoundry', defaultBranch: 'main' } });
        const ownerNode = await this.contextStore.createNode({ tenantId, aclId, kind: 'owner', sourceId: 'admin@devfoundry.local', revision: 'HEAD', metadata: { email: 'admin@devfoundry.local', role: 'admin' } });
        const svcNode = await this.contextStore.createNode({ tenantId, aclId, kind: 'service', sourceId: 'routeforge', revision: 'HEAD', metadata: { name: 'routeforge', port: 8000 } });
        const docNode = await this.contextStore.createNode({ tenantId, aclId, kind: 'document', sourceId: 'DEVFOUNDRY_ARCHITECTURE.md', revision: 'HEAD', metadata: { name: 'Architecture', path: 'DEVFOUNDRY_ARCHITECTURE.md' } });
        await this.contextStore.createEdge({ sourceId: repoNode.id, destinationId: ownerNode.id, relationType: 'owned-by', scope: tenantId, revision: 'HEAD', aclId, provenance: { seeded: true } });
        await this.contextStore.createEdge({ sourceId: repoNode.id, destinationId: svcNode.id, relationType: 'served-by', scope: tenantId, revision: 'HEAD', aclId, provenance: { seeded: true } });
        await this.contextStore.createEdge({ sourceId: docNode.id, destinationId: repoNode.id, relationType: 'describes', scope: tenantId, revision: 'HEAD', aclId, provenance: { seeded: true } });
        await this.contextStore.addChunk({ contextNodeId: repoNode.id, location: 'DEVFOUNDRY_ARCHITECTURE.md', revision: 'HEAD', text: 'DevFoundry is an on-premises software factory: request -> isolated patch -> clean validation -> review packet -> optional draft PR.' });
        await this.contextStore.addChunk({ contextNodeId: svcNode.id, location: 'k8s/dev-foundry.yaml', revision: 'HEAD', text: 'RouteForge model gateway runs on port 8000 behind fail-closed app-token auth.' });
      }

      try {
        const admin = this.getRouteForgeAdmin();
        await admin.login();
        const models = await admin.listModels();
        if (Array.isArray(models) && models.length === 0) {
          await admin.onboardModel({
            slug: 'glm-5.3-flash',
            display_name: 'GLM 5.3 Flash (on-prem)',
            tier: 'mid',
            endpoint: 'http://routeforge:8000/v1',
            price_input: 0,
            price_output: 0,
            enabled: true,
            notes: 'Seeded by DevFoundry; on-prem resident model',
          });
        }
      } catch {
        // gateway may be unavailable at startup; non-fatal
      }
    } catch (err) {
      console.error('[api] Seed failed (non-fatal):', err instanceof Error ? err.message : err);
    }
  }

  private mapTask(row: Record<string, unknown>) {
    return {
      id: row.id,
      tenantId: row.tenant_id,
      projectId: row.project_id,
      userId: row.user_id,
      status: row.status,
      phase: row.phase,
      description: row.description,
      baseCommit: row.base_commit,
      targetBranch: row.target_branch,
      workspaceId: row.workspace_id,
      skills: row.skills || [],
      contextIds: row.context_ids || [],
      toolPermissions: row.tool_permissions || [],
      modelRoute: row.model_route,
      capacityProfile: row.capacity_profile,
      createdAt: row.created_at,
      updatedAt: row.updated_at,
      startedAt: row.started_at,
      completedAt: row.completed_at,
      retryCount: row.retry_count,
      checkpoint: row.checkpoint,
      outcome: row.outcome,
    };
  }

  private async probeService(
    name: string,
    url: string,
    path: string,
    timeoutMs = 3000
  ): Promise<{ name: string; status: string; latencyMs?: number; detail?: Record<string, unknown> }> {
    const started = Date.now();
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeoutMs);
      const res = await fetch(`${url}${path}`, { signal: controller.signal });
      clearTimeout(timer);
      const latencyMs = Date.now() - started;
      let detail: Record<string, unknown> = {};
      try {
        detail = (await res.json()) as Record<string, unknown>;
      } catch {
        detail = {};
      }
      return { name, status: res.ok ? 'ok' : 'error', latencyMs, detail };
    } catch (err) {
      return { name, status: 'unavailable', detail: { error: (err as Error).message } };
    }
  }

  private setupRoutes(): void {
    this.app.use(express.json());

    this.app.get('/health', (req: Request, res: Response) => {
      res.json({ status: 'ok' });
    });

    this.app.get('/api/health', async (req: Request, res: Response) => {
      let dbStatus = 'connected';
      try {
        await this.pool.query('SELECT 1');
      } catch {
        dbStatus = 'unavailable';
      }

      const uptime = Math.floor((Date.now() - this.startTime) / 1000);

      const serviceUrls: Array<{ name: string; env: string; fallback: string; path: string }> = [
        { name: 'routeforge', env: 'ROUTEFORGE_URL', fallback: 'http://routeforge:8000', path: '/health' },
        { name: 'contextForge', env: 'CONTEXFORGE_URL', fallback: 'http://contextforge:4444', path: '/health' },
        { name: 'openCode', env: 'OPENCODE_URL', fallback: 'http://opencode:4096', path: '/' },
      ];
      const probes = await Promise.all(
        serviceUrls.map((s) => this.probeService(s.name, process.env[s.env] || s.fallback, s.path))
      );

      let workerStatus = 'unavailable';
      let workerDetail: Record<string, unknown> = {};
      try {
        const rows = await this.pool.query(
          `SELECT COUNT(*)::int AS c FROM tasks WHERE phase IN ('Submitted','Qualified','Running','Validating')`
        );
        workerStatus = 'ok';
        workerDetail = { queueDepth: rows[0]?.c ?? 0 };
      } catch {
        workerStatus = 'unavailable';
      }

      const total = os.totalmem();
      const free = os.freemem();
      res.json({
        status: 'ok',
        uptime,
        services: {
          api: { status: 'ok', uptime },
          database: { status: dbStatus },
          worker: { status: workerStatus, ...workerDetail },
          ...Object.fromEntries(probes.map((p) => [p.name, { status: p.status, latencyMs: p.latencyMs, detail: p.detail }])),
        },
        resources: {
          cpu: { usage: Math.min(100, (os.loadavg()[0] / os.cpus().length) * 100) },
          memory: { usage: Math.round(((total - free) / total) * 100) },
        },
      });
    });

    this.app.post('/api/auth/login', (req: Request, res: Response) => {
      const { email, password } = req.body || {};

      if (!email || !password) {
        return res.status(400).json({ error: 'Email and password are required' });
      }

      const adminEmail = process.env.PLATFORM_ADMIN_EMAIL || 'admin@devfoundry.local';
      const adminPassword = process.env.PLATFORM_ADMIN_PASSWORD || 'devfoundry';

      if (email === adminEmail && password === adminPassword) {
        const token = this.generateAuthToken(email);
        return res.json({ token, user: { email } });
      }

      return res.status(401).json({ error: 'Invalid credentials' });
    });

    this.app.get('/api/tasks', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const { tenantId, projectId, userId, status, phase } = req.query;
        const limit = Math.min(parseInt(String(req.query.limit || '50'), 10) || 50, 200);
        const offset = parseInt(String(req.query.offset || '0'), 10) || 0;

        const conditions: string[] = [];
        const params: unknown[] = [];
        const addCondition = (col: string, value: unknown) => {
          params.push(value);
          conditions.push(`${col} = $${params.length}`);
        };

        if (tenantId) addCondition('tenant_id::text', tenantId);
        if (projectId) addCondition('project_id::text', projectId);
        if (userId) addCondition('user_id::text', userId);
        if (status) addCondition('status', status);
        if (phase) addCondition('phase', phase);

        const where = conditions.length ? `WHERE ${conditions.join(' AND ')}` : '';
        const countResult = await this.pool.query(`SELECT COUNT(*)::int AS total FROM tasks ${where}`, params);
        const result = await this.pool.query(
          `SELECT * FROM tasks ${where} ORDER BY created_at DESC LIMIT ${limit} OFFSET ${offset}`,
          params
        );

        res.json({
          tasks: result.rows.map((r) => this.mapTask(r)),
          total: countResult.rows[0]?.total ?? 0,
          limit,
          offset,
        });
      } catch (err) {
        next(err);
      }
    });

    this.app.get('/api/tasks/:id', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const result = await this.pool.query('SELECT * FROM tasks WHERE id = $1', [req.params.id]);
        if (result.rows.length === 0) {
          return res.status(404).json({ error: 'Task not found' });
        }
        res.json(this.mapTask(result.rows[0]));
      } catch (err) {
        next(err);
      }
    });

    this.app.post('/api/tasks', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const { description, projectId, userId, tenantId, baseCommit, targetBranch, skills, contextIds, modelRoute, capacityProfile } = req.body || {};

        if (!description || !projectId || !userId) {
          return res.status(400).json({ error: 'description, projectId and userId are required' });
        }

        const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
        const asUuid = (v: string, fallback: string) => (UUID_RE.test(v) ? v : fallback);

        const id = uuidv4();
        const result = await this.pool.query(
          `INSERT INTO tasks (id, tenant_id, project_id, user_id, status, phase, description,
             base_commit, target_branch, workspace_id, skills, context_ids, tool_permissions,
             model_route, capacity_profile)
           VALUES ($1, $2, $3, $4, 'Pending', 'Submitted', $5, $6, $7, $8, $9, $10, $11, $12, $13)
           RETURNING *`,
          [
            id,
            asUuid(String(tenantId || ''), uuidv4()),
            asUuid(String(projectId), uuidv4()),
            asUuid(String(userId), uuidv4()),
            description,
            baseCommit || 'HEAD',
            targetBranch || 'main',
            uuidv4(),
            JSON.stringify(skills || []),
            contextIds || [],
            JSON.stringify([]),
            modelRoute || 'default',
            capacityProfile || 'default',
          ]
        );
        res.status(201).json(this.mapTask(result.rows[0]));
      } catch (err) {
        next(err);
      }
    });

    this.app.patch('/api/tasks/:id', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const { status, phase, outcome, checkpoint, completedAt, startedAt, retryCount } = req.body || {};

        const updates: string[] = [];
        const params: unknown[] = [];
        const set = (col: string, value: unknown) => {
          params.push(value);
          updates.push(`${col} = $${params.length}`);
        };

        if (status !== undefined) set('status', status);
        if (phase !== undefined) set('phase', phase);
        if (outcome !== undefined) set('outcome', JSON.stringify(outcome));
        if (checkpoint !== undefined) set('checkpoint', JSON.stringify(checkpoint));
        if (completedAt !== undefined) set('completed_at', completedAt);
        if (startedAt !== undefined) set('started_at', startedAt);
        if (retryCount !== undefined) set('retry_count', retryCount);

        if (updates.length === 0) {
          return res.status(400).json({ error: 'No updatable fields provided' });
        }

        if (status === 'Completed' || status === 'Cancelled' || status === 'Failed') {
          if (completedAt === undefined) {
            params.push(new Date().toISOString());
            updates.push(`completed_at = $${params.length}`);
          }
        }

        updates.push(`updated_at = NOW()`);
        params.push(req.params.id);

        const result = await this.pool.query(
          `UPDATE tasks SET ${updates.join(', ')} WHERE id = $${params.length} RETURNING *`,
          params
        );
        if (result.rows.length === 0) {
          return res.status(404).json({ error: 'Task not found' });
        }
        res.json(this.mapTask(result.rows[0]));
      } catch (err) {
        next(err);
      }
    });

    this.app.delete('/api/tasks/:id', async (req: Request, res: Response, next: NextFunction) => {
      try {
        await this.pool.query('DELETE FROM task_outcomes WHERE task_id = $1', [req.params.id]);
        const result = await this.pool.query('DELETE FROM tasks WHERE id = $1 RETURNING id', [req.params.id]);
        if (result.rows.length === 0) {
          return res.status(404).json({ error: 'Task not found' });
        }
        res.json({ deleted: result.rows[0].id });
      } catch (err) {
        next(err);
      }
    });

    // Task actions and workspace routes
    this.app.post('/api/tasks/:id/cancel', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const result = await this.pool.query('SELECT status, phase, workspace_id FROM tasks WHERE id = $1', [req.params.id]);
        if (result.rows.length === 0) {
          return res.status(404).json({ error: 'Task not found' });
        }
        const task = result.rows[0];
        if (['Completed', 'Failed', 'Cancelled'].includes(String(task.status))) {
          return res.status(400).json({ error: 'Task already terminal' });
        }

        const updateResult = await this.pool.query(
          `UPDATE tasks
           SET status = 'Cancelled', phase = 'Cancelled', updated_at = NOW(),
               completed_at = COALESCE(completed_at, NOW())
           WHERE id = $1
           RETURNING *`,
          [req.params.id]
        );

        const workspaceId = task.workspace_id;
        if (workspaceId) {
          try {
            const opencodeUrl = process.env.OPENCODE_URL || 'http://opencode:4096';
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), 2000);
            try {
              await fetch(`${opencodeUrl}/session/${String(workspaceId)}/abort`, { method: 'POST', signal: controller.signal });
            } finally {
              clearTimeout(timer);
            }
          } catch {
            // best-effort abort; non-fatal
          }
        }

        res.json(this.mapTask(updateResult.rows[0]));
      } catch (err) {
        next(err);
      }
    });

    this.app.post('/api/tasks/:id/approve', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const exists = await this.pool.query('SELECT phase FROM tasks WHERE id = $1', [req.params.id]);
        if (exists.rows.length === 0) {
          return res.status(404).json({ error: 'Task not found' });
        }
        if (String(exists.rows[0].phase) !== 'AwaitingReview') {
          return res.status(400).json({ error: 'Task is not awaiting review' });
        }

        const { disposition, reason } = (req.body || {}) as { disposition?: 'approve' | 'reject'; reason?: string };
        const effectiveDisposition = disposition || 'approve';

        const outcome = effectiveDisposition === 'reject'
          ? { success: false, reason: reason || 'Rejected at review' }
          : { success: true, reason: reason || 'Approved at review' };

        const status = effectiveDisposition === 'reject' ? 'Failed' : 'Completed';
        const updateResult = await this.pool.query(
          `UPDATE tasks
           SET status = $2, phase = $2, outcome = $3,
               completed_at = CASE WHEN $2 = 'Completed' THEN NOW() ELSE completed_at END
           WHERE id = $1
           RETURNING *`,
          [req.params.id, status, JSON.stringify(outcome)]
        );

        await this.pool.query(
          `INSERT INTO task_outcomes (id, task_id, attempt_id, success, reason, evidence, trace_references)
           VALUES ($1, $2, $3, $4, $5, '[]'::jsonb, '[]'::jsonb)`,
          [uuidv4(), req.params.id, uuidv4(), outcome.success, outcome.reason]
        );

        res.json(this.mapTask(updateResult.rows[0]));
      } catch (err) {
        next(err);
      }
    });

    this.app.post('/api/tasks/:id/retry', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const exists = await this.pool.query('SELECT id, status FROM tasks WHERE id = $1', [req.params.id]);
        if (exists.rows.length === 0) {
          return res.status(404).json({ error: 'Task not found' });
        }
        if (String(exists.rows[0].status) !== 'Failed') {
          return res.status(400).json({ error: 'Only failed tasks can be retried' });
        }
        const updateResult = await this.pool.query(
          `UPDATE tasks
           SET status = 'Pending', phase = 'Submitted', retry_count = retry_count + 1,
               outcome = NULL, completed_at = NULL, updated_at = NOW()
           WHERE id = $1
           RETURNING *`,
          [req.params.id]
        );
        res.json(this.mapTask(updateResult.rows[0]));
      } catch (err) {
        next(err);
      }
    });

    this.app.post('/api/tasks/:id/pause', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const exists = await this.pool.query('SELECT id, status, phase FROM tasks WHERE id = $1', [req.params.id]);
        if (exists.rows.length === 0) {
          return res.status(404).json({ error: 'Task not found' });
        }
        if (String(exists.rows[0].status) !== 'Pending' || String(exists.rows[0].phase) !== 'Running') {
          return res.status(400).json({ error: 'Only running tasks can be paused' });
        }
        const updateResult = await this.pool.query(
          `UPDATE tasks SET status = 'Paused', phase = 'Paused', updated_at = NOW() WHERE id = $1 RETURNING *`,
          [req.params.id]
        );
        res.json(this.mapTask(updateResult.rows[0]));
      } catch (err) {
        next(err);
      }
    });

    this.app.post('/api/tasks/:id/resume', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const exists = await this.pool.query('SELECT id, status FROM tasks WHERE id = $1', [req.params.id]);
        if (exists.rows.length === 0) {
          return res.status(404).json({ error: 'Task not found' });
        }
        if (String(exists.rows[0].status) !== 'Paused') {
          return res.status(400).json({ error: 'Task is not paused' });
        }
        const updateResult = await this.pool.query(
          `UPDATE tasks SET status = 'Pending', phase = 'Qualified', updated_at = NOW() WHERE id = $1 RETURNING *`,
          [req.params.id]
        );
        res.json(this.mapTask(updateResult.rows[0]));
      } catch (err) {
        next(err);
      }
    });

    this.app.get('/api/workspaces/:id', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const opencodeUrl = process.env.OPENCODE_URL || 'http://opencode:4096';
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 3000);
        let opencodeRes: Awaited<ReturnType<typeof fetch>>;
        try {
          opencodeRes = await fetch(`${opencodeUrl}/session/${String(req.params.id)}`, { signal: controller.signal });
        } finally {
          clearTimeout(timer);
        }
        if (!opencodeRes.ok) {
          return res.status(404).json({ error: 'Workspace not found' });
        }
        const session = await opencodeRes.json();
        res.json({ workspace: session });
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') {
          return res.status(502).json({ error: 'OpenCode unavailable' });
        }
        next(err);
      }
    });

    // Quality and admission routes
    this.app.get('/api/tasks/:id/review-packet', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const result = await this.pool.query(
          `SELECT payload, created_at FROM event_log
           WHERE event_type = 'review_packet_generated' AND entity_type = 'task' AND entity_id = $1
           ORDER BY created_at DESC LIMIT 1`,
          [req.params.id]
        );
        if (result.rows.length === 0) {
          return res.status(404).json({ error: 'Review packet not found' });
        }
        res.json({ packet: result.rows[0].payload, generatedAt: result.rows[0].created_at });
      } catch (err) {
        next(err);
      }
    });

    this.app.get('/api/analytics/outcomes', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const { tenantId, projectId } = req.query;
        const days = Math.min(parseInt(String(req.query.days || '30'), 10) || 30, 365);

        const params: unknown[] = [String(days)];
        const conditions: string[] = [];
        const addCondition = (col: string, value: unknown) => {
          params.push(value);
          conditions.push(`${col} = $${params.length}`);
        };

        if (tenantId) addCondition('tenant_id::text', tenantId);
        if (projectId) addCondition('project_id::text', projectId);

        const filters = conditions.length ? ` AND ${conditions.join(' AND ')}` : '';

        const result = await this.pool.query(
          `SELECT
             COUNT(*)::int AS total_tasks,
             SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END)::int AS completed_count,
             SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END)::int AS failed_count,
             SUM(CASE WHEN status = 'Cancelled' THEN 1 ELSE 0 END)::int AS cancelled_count,
             SUM(CASE WHEN status = 'Pending' THEN 1 ELSE 0 END)::int AS pending_count,
             AVG(retry_count) AS avg_retries,
             AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) AS avg_duration_s
           FROM tasks WHERE created_at >= NOW() - ($1 || ' days')::interval${filters}`,
          params
        );
        res.json(result.rows[0] || {});
      } catch (err) {
        next(err);
      }
    });

    this.app.get('/api/analytics/phases', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const { tenantId, projectId } = req.query;

        const conditions: string[] = [];
        const params: unknown[] = [];
        const addCondition = (col: string, value: unknown) => {
          params.push(value);
          conditions.push(`${col} = $${params.length}`);
        };

        if (tenantId) addCondition('tenant_id::text', tenantId);
        if (projectId) addCondition('project_id::text', projectId);

        const where = conditions.length ? `WHERE ${conditions.join(' AND ')}` : '';

        const result = await this.pool.query(
          `SELECT phase, COUNT(*)::int AS count FROM tasks ${where} GROUP BY phase ORDER BY count DESC`,
          params
        );
        res.json({ phases: result.rows });
      } catch (err) {
        next(err);
      }
    });

    this.app.get('/api/admission', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const queue = await this.pool.query(
          `SELECT COUNT(*)::int AS c FROM tasks WHERE phase IN ('Submitted','Qualified','Running','Validating')`
        );
        const awaiting = await this.pool.query(
          `SELECT COUNT(*)::int AS c FROM tasks WHERE phase = 'AwaitingReview'`
        );
        res.json({
          limits: {
            cpu: Number(process.env.ADMISSION_CPU_LIMIT || '8'),
            ram: Number(process.env.ADMISSION_RAM_LIMIT || '16'),
            disk: Number(process.env.ADMISSION_DISK_LIMIT || '100'),
          },
          queue: { depth: queue.rows[0]?.c ?? 0, awaitingReview: awaiting.rows[0]?.c ?? 0 },
          resources: {
            cpu: { usage: Math.min(100, (os.loadavg()[0] / os.cpus().length) * 100) },
            memory: { usage: Math.round(((os.totalmem() - os.freemem()) / os.totalmem()) * 100) },
          },
        });
      } catch (err) {
        next(err);
      }
    });

    this.app.get('/api/outcomes/:taskId', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const result = await this.pool.query(
          'SELECT * FROM task_outcomes WHERE task_id = $1 ORDER BY created_at DESC LIMIT 1',
          [req.params.taskId]
        );
        if (result.rows.length === 0) {
          return res.status(404).json({ error: 'Outcome not found' });
        }
        res.json({ outcome: result.rows[0] });
      } catch (err) {
        next(err);
      }
    });

    this.app.get('/api/tasks/:id/attempts', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const result = await this.pool.query(
          'SELECT attempt_id, success, reason, created_at FROM task_outcomes WHERE task_id = $1 ORDER BY created_at ASC',
          [req.params.id]
        );
        res.json({ attempts: result.rows });
      } catch (err) {
        next(err);
      }
    });

    this.app.get('/api/tasks/:id/outcomes', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const result = await this.pool.query(
          'SELECT * FROM task_outcomes WHERE task_id = $1 ORDER BY created_at DESC',
          [req.params.id]
        );
        res.json({
          outcomes: result.rows.map((r) => ({
            id: r.id,
            taskId: r.task_id,
            attemptId: r.attempt_id,
            success: r.success,
            reason: r.reason,
            evidence: r.evidence || [],
            traceReferences: r.trace_references || [],
            createdAt: r.created_at,
          })),
        });
      } catch (err) {
        next(err);
      }
    });

    this.app.get('/api/tasks/:id/evidence', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const result = await this.pool.query(
          'SELECT evidence, created_at FROM task_outcomes WHERE task_id = $1 ORDER BY created_at DESC',
          [req.params.id]
        );
        const evidence = result.rows.flatMap((r) => (Array.isArray(r.evidence) ? r.evidence : []));
        res.json({ evidence });
      } catch (err) {
        next(err);
      }
    });

    this.app.post('/api/tasks/:id/evidence', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const { type, content, provenance } = req.body || {};
        if (!type || !content) {
          return res.status(400).json({ error: 'type and content are required' });
        }
        const exists = await this.pool.query('SELECT id FROM tasks WHERE id = $1', [req.params.id]);
        if (exists.rows.length === 0) {
          return res.status(404).json({ error: 'Task not found' });
        }
        const item = { type, content, timestamp: new Date().toISOString(), provenance: provenance || {} };
        await this.pool.query(
          `INSERT INTO task_outcomes (id, task_id, attempt_id, success, evidence, trace_references)
           VALUES ($1, $2, $3, true, $4, $5)`,
          [uuidv4(), req.params.id, uuidv4(), JSON.stringify([item]), JSON.stringify([])]
        );
        res.status(201).json(item);
      } catch (err) {
        next(err);
      }
    });

    // ---- Context graph ----
    this.app.get('/api/context/stats', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const tenantId = String(req.query.tenantId || '00000000-0000-0000-0000-000000000000');
        res.json(await this.contextStore.stats(tenantId));
      } catch (err) { next(err); }
    });

    this.app.get('/api/context/nodes', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const tenantId = String(req.query.tenantId || '00000000-0000-0000-0000-000000000000');
        res.json({
          nodes: await this.contextStore.listNodes(tenantId, {
            kind: req.query.kind ? String(req.query.kind) : undefined,
            projectId: req.query.projectId ? String(req.query.projectId) : undefined,
            limit: req.query.limit ? parseInt(String(req.query.limit), 10) : undefined,
          }),
        });
      } catch (err) { next(err); }
    });

    this.app.post('/api/context/nodes', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const { tenantId, projectId, kind, sourceId, revision, aclId, metadata } = req.body || {};
        if (!tenantId || !kind || !sourceId) {
          return res.status(400).json({ error: 'tenantId, kind, sourceId are required' });
        }
        const node = await this.contextStore.createNode({
          tenantId, projectId, kind, sourceId,
          revision: revision || 'HEAD',
          aclId: aclId || '00000000-0000-0000-0000-000000000000',
          metadata: metadata || {},
        });
        res.status(201).json(node);
      } catch (err) { next(err); }
    });

    this.app.get('/api/context/edges', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const tenantId = String(req.query.tenantId || '00000000-0000-0000-0000-000000000000');
        res.json({
          edges: await this.contextStore.listEdges(tenantId, {
            nodeId: req.query.nodeId ? String(req.query.nodeId) : undefined,
            relationType: req.query.relationType ? String(req.query.relationType) : undefined,
            limit: req.query.limit ? parseInt(String(req.query.limit), 10) : undefined,
          }),
        });
      } catch (err) { next(err); }
    });

    this.app.post('/api/context/edges', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const { sourceId, destinationId, relationType, scope, revision, aclId, provenance } = req.body || {};
        if (!sourceId || !destinationId || !relationType || !scope) {
          return res.status(400).json({ error: 'sourceId, destinationId, relationType, scope are required' });
        }
        const edge = await this.contextStore.createEdge({ sourceId, destinationId, relationType, scope, revision: revision || 'HEAD', aclId: aclId || '00000000-0000-0000-0000-000000000000', provenance: provenance || {} });
        res.status(201).json(edge);
      } catch (err) { next(err); }
    });

    this.app.get('/api/context/search', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const q = String(req.query.q || '');
        if (!q) return res.status(400).json({ error: 'q is required' });
        const tenantId = String(req.query.tenantId || '00000000-0000-0000-0000-000000000000');
        res.json({ results: await this.contextStore.searchChunks(tenantId, q) });
      } catch (err) { next(err); }
    });

    this.app.post('/api/context/traverse', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const { startNodeId, tenantId, maxHops, relationType } = req.body || {};
        if (!startNodeId) return res.status(400).json({ error: 'startNodeId is required' });
        res.json(await this.contextStore.traverse(tenantId || '00000000-0000-0000-0000-000000000000', startNodeId, { maxHops, relationType }));
      } catch (err) { next(err); }
    });

    this.app.post('/api/context/chunks', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const { contextNodeId, location, revision, text } = req.body || {};
        if (!contextNodeId || !location || !text) {
          return res.status(400).json({ error: 'contextNodeId, location, text are required' });
        }
        const chunk = await this.contextStore.addChunk({ contextNodeId, location, revision: revision || 'HEAD', text });
        res.status(201).json(chunk);
      } catch (err) { next(err); }
    });

    // ---- Memory ----
    this.app.get('/api/memory', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const ownerId = String(req.query.ownerId || '00000000-0000-0000-0000-000000000000');
        res.json({
          records: await this.memoryStore.list(ownerId, {
            scope: req.query.scope ? String(req.query.scope) : undefined,
            scopeId: req.query.scopeId ? String(req.query.scopeId) : undefined,
            type: req.query.type ? String(req.query.type) : undefined,
            promotedOnly: req.query.promoted === 'true',
            limit: req.query.limit ? parseInt(String(req.query.limit), 10) : undefined,
          }),
        });
      } catch (err) { next(err); }
    });

    this.app.post('/api/memory', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const { ownerId, scope, scopeId, type, content, provenance, revision, ttl, confidence } = req.body || {};
        if (!ownerId || !scope || !scopeId || !type || !content) {
          return res.status(400).json({ error: 'ownerId, scope, scopeId, type, content are required' });
        }
        const record = await this.memoryStore.create({ ownerId, scope, scopeId, type, content, provenance, revision: revision || 'HEAD', ttl, confidence });
        res.status(201).json(record);
      } catch (err) { next(err); }
    });

    this.app.get('/api/memory/:id', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const record = await this.memoryStore.get(req.params.id);
        if (!record) return res.status(404).json({ error: 'Memory record not found' });
        res.json(record);
      } catch (err) { next(err); }
    });

    this.app.patch('/api/memory/:id', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const record = await this.memoryStore.update(req.params.id, req.body || {});
        if (!record) return res.status(404).json({ error: 'Memory record not found' });
        res.json(record);
      } catch (err) { next(err); }
    });

    this.app.post('/api/memory/:id/promote', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const record = await this.memoryStore.promote(req.params.id);
        if (!record) return res.status(404).json({ error: 'Memory record not found' });
        res.json(record);
      } catch (err) { next(err); }
    });

    this.app.delete('/api/memory/:id', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const deleted = await this.memoryStore.delete(req.params.id);
        if (!deleted) return res.status(404).json({ error: 'Memory record not found' });
        res.json({ deleted: true });
      } catch (err) { next(err); }
    });

    // ---- Skills catalog ----
    this.app.get('/api/skills', async (req: Request, res: Response, next: NextFunction) => {
      try {
        res.json({
          skills: await this.skillStore.list({
            status: req.query.status ? String(req.query.status) : undefined,
            limit: req.query.limit ? parseInt(String(req.query.limit), 10) : undefined,
          }),
        });
      } catch (err) { next(err); }
    });

    this.app.get('/api/skills/:id', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const skill = await this.skillStore.get(req.params.id);
        if (!skill) return res.status(404).json({ error: 'Skill not found' });
        res.json(skill);
      } catch (err) { next(err); }
    });

    this.app.post('/api/skills', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const { name, path, gitRepository, version, description, gitCommit, approvalStatus, ownerId, metadata, tests, capabilityManifest } = req.body || {};
        if (!name || !path || !gitRepository) {
          return res.status(400).json({ error: 'name, path, gitRepository are required' });
        }
        const skill = await this.skillStore.install({ name, path, gitRepository, version, description, gitCommit, approvalStatus, ownerId, metadata, tests, capabilityManifest });
        res.status(201).json(skill);
      } catch (err) { next(err); }
    });

    this.app.patch('/api/skills/:id/status', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const { status } = req.body || {};
        if (!status) return res.status(400).json({ error: 'status is required' });
        const skill = await this.skillStore.updateStatus(req.params.id, status);
        if (!skill) return res.status(404).json({ error: 'Skill not found' });
        res.json(skill);
      } catch (err) {
        if (err instanceof Error && err.message.startsWith('Invalid approval status')) {
          return res.status(400).json({ error: err.message });
        }
        next(err);
      }
    });

    this.app.post('/api/skills/approve-by-digest', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const { digest } = req.body || {};
        if (!digest) return res.status(400).json({ error: 'digest is required' });
        const skill = await this.skillStore.approveByDigest(digest);
        if (!skill) return res.status(404).json({ error: 'No skill with that digest' });
        res.json(skill);
      } catch (err) { next(err); }
    });

    // Model gateway admin (RouteForge) routes
    this.app.get('/api/gateway/models', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const admin = this.getRouteForgeAdmin();
        await admin.login();
        res.json({ models: await admin.listModels() });
      } catch (err) { next(err); }
    });

    this.app.post('/api/gateway/models', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const body = req.body || {};
        if (!body.slug || !body.displayName || !body.tier || !body.endpoint || body.priceInput === undefined || body.priceOutput === undefined) {
          return res.status(400).json({ error: 'slug, displayName, tier, endpoint, priceInput and priceOutput are required' });
        }
        const priceInput = Number(body.priceInput);
        const priceOutput = Number(body.priceOutput);
        if (Number.isNaN(priceInput) || Number.isNaN(priceOutput)) {
          return res.status(400).json({ error: 'priceInput and priceOutput must be numbers' });
        }
        const model: Record<string, unknown> = {
          slug: body.slug,
          display_name: body.displayName,
          tier: body.tier,
          endpoint: body.endpoint,
          price_input: priceInput,
          price_output: priceOutput,
        };
        if (body.apiKeyEnv !== undefined) model.api_key_env = body.apiKeyEnv;
        if (body.priceCachedInput !== undefined) model.price_cached_input = body.priceCachedInput;
        if (body.quality !== undefined) model.quality = body.quality;
        if (body.contextWindow !== undefined) model.context_window = body.contextWindow;
        if (body.allowedAppIds !== undefined) model.allowed_app_ids = body.allowedAppIds;
        if (body.notes !== undefined) model.notes = body.notes;
        if (body.enabled !== undefined) model.enabled = body.enabled;
        if (body.region !== undefined) model.region = body.region;
        if (body.promptRetention !== undefined) model.prompt_retention = body.promptRetention;
        if (body.acceptsRawSensitive !== undefined) model.accepts_raw_sensitive = body.acceptsRawSensitive;
        const admin = this.getRouteForgeAdmin();
        await admin.login();
        res.status(201).json(await admin.onboardModel(model as never));
      } catch (err) { next(err); }
    });

    this.app.put('/api/gateway/models/:slug', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const slug = String(req.params.slug || '');
        if (!slug) return res.status(400).json({ error: 'slug is required' });
        const body = req.body || {};
        if (!body.slug || !body.displayName || !body.tier || !body.endpoint || body.priceInput === undefined || body.priceOutput === undefined) {
          return res.status(400).json({ error: 'slug, displayName, tier, endpoint, priceInput and priceOutput are required' });
        }
        const priceInput = Number(body.priceInput);
        const priceOutput = Number(body.priceOutput);
        if (Number.isNaN(priceInput) || Number.isNaN(priceOutput)) {
          return res.status(400).json({ error: 'priceInput and priceOutput must be numbers' });
        }
        const model: Record<string, unknown> = {
          slug: body.slug,
          display_name: body.displayName,
          tier: body.tier,
          endpoint: body.endpoint,
          price_input: priceInput,
          price_output: priceOutput,
        };
        if (body.apiKeyEnv !== undefined) model.api_key_env = body.apiKeyEnv;
        if (body.priceCachedInput !== undefined) model.price_cached_input = body.priceCachedInput;
        if (body.quality !== undefined) model.quality = body.quality;
        if (body.contextWindow !== undefined) model.context_window = body.contextWindow;
        if (body.allowedAppIds !== undefined) model.allowed_app_ids = body.allowedAppIds;
        if (body.notes !== undefined) model.notes = body.notes;
        if (body.enabled !== undefined) model.enabled = body.enabled;
        if (body.region !== undefined) model.region = body.region;
        if (body.promptRetention !== undefined) model.prompt_retention = body.promptRetention;
        if (body.acceptsRawSensitive !== undefined) model.accepts_raw_sensitive = body.acceptsRawSensitive;
        const admin = this.getRouteForgeAdmin();
        await admin.login();
        res.json(await admin.editModel(slug, model as never));
      } catch (err) { next(err); }
    });

    this.app.delete('/api/gateway/models/:slug', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const slug = String(req.params.slug || '');
        if (!slug) return res.status(400).json({ error: 'slug is required' });
        const admin = this.getRouteForgeAdmin();
        await admin.login();
        await admin.deleteModel(slug);
        res.json({ deleted: true, slug });
      } catch (err) { next(err); }
    });

    this.app.get('/api/gateway/applications', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const admin = this.getRouteForgeAdmin();
        await admin.login();
        res.json({ applications: await admin.listApplications() });
      } catch (err) { next(err); }
    });

    this.app.post('/api/gateway/applications', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const body = req.body || {};
        if (!body.id || !body.name) {
          return res.status(400).json({ error: 'id and name are required' });
        }
        const app: Record<string, unknown> = { id: body.id, name: body.name };
        if (body.ownerEmail !== undefined) app.owner_email = body.ownerEmail;
        if (body.defaultResidency !== undefined) app.default_residency = body.defaultResidency;
        const admin = this.getRouteForgeAdmin();
        await admin.login();
        res.status(201).json(await admin.createApplication(app as never));
      } catch (err) { next(err); }
    });

    this.app.get('/api/gateway/applications/:id', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const admin = this.getRouteForgeAdmin();
        await admin.login();
        res.json(await admin.getApplication(String(req.params.id)));
      } catch (err) { next(err); }
    });

    this.app.patch('/api/gateway/applications/:id', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const body = req.body || {};
        const update: Record<string, unknown> = {};
        if (body.name !== undefined) update.name = body.name;
        if (body.ownerEmail !== undefined) update.owner_email = body.ownerEmail;
        if (body.status !== undefined) update.status = body.status;
        if (body.defaultResidency !== undefined) update.default_residency = body.defaultResidency;
        if (Object.keys(update).length === 0) {
          return res.status(400).json({ error: 'No updatable fields provided' });
        }
        const admin = this.getRouteForgeAdmin();
        await admin.login();
        res.json(await admin.updateApplication(String(req.params.id), update as never));
      } catch (err) { next(err); }
    });

    this.app.post('/api/gateway/applications/:id/tokens', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const { name } = req.body || {};
        const admin = this.getRouteForgeAdmin();
        await admin.login();
        res.status(201).json(await admin.createApplicationToken(String(req.params.id), name ? String(name) : undefined));
      } catch (err) { next(err); }
    });

    this.app.post('/api/gateway/tokens/:tokenId/revoke', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const admin = this.getRouteForgeAdmin();
        await admin.login();
        res.json(await admin.revokeToken(String(req.params.tokenId)));
      } catch (err) { next(err); }
    });

    this.app.put('/api/gateway/applications/:id/policy', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const body = req.body || {};
        const policy: Record<string, unknown> = {};
        if (body.allowedTiers !== undefined) policy.allowed_tiers = body.allowedTiers;
        if (body.allowedProviders !== undefined) policy.allowed_providers = body.allowedProviders;
        if (body.allowedModels !== undefined) policy.allowed_models = body.allowedModels;
        if (body.residency !== undefined) policy.residency = body.residency;
        if (body.maxSpendUsdPerDay !== undefined) policy.max_spend_usd_per_day = body.maxSpendUsdPerDay;
        if (body.maxCostUsdPerRequest !== undefined) policy.max_cost_usd_per_request = body.maxCostUsdPerRequest;
        if (Object.keys(policy).length === 0) {
          return res.status(400).json({ error: 'No policy fields provided' });
        }
        const admin = this.getRouteForgeAdmin();
        await admin.login();
        res.json(await admin.setPolicy(String(req.params.id), policy as never));
      } catch (err) { next(err); }
    });

    // ---- MCP tool registry ----
    this.app.get('/api/tools', async (req: Request, res: Response, next: NextFunction) => {
      try {
        res.json({
          tools: await this.toolRegistry.list({
            enabledOnly: req.query.enabled === 'true',
            kind: req.query.kind ? String(req.query.kind) : undefined,
            limit: req.query.limit ? parseInt(String(req.query.limit), 10) : undefined,
          }),
        });
      } catch (err) { next(err); }
    });

    this.app.get('/api/tools/search', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const q = String(req.query.q || '');
        if (!q) return res.status(400).json({ error: 'q is required' });
        res.json({
          tools: await this.toolRegistry.search(q, { enabledOnly: req.query.enabled === 'true' }),
        });
      } catch (err) { next(err); }
    });

    this.app.get('/api/tools/:id', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const tool = await this.toolRegistry.get(req.params.id);
        if (!tool) return res.status(404).json({ error: 'Tool not found' });
        res.json(tool);
      } catch (err) { next(err); }
    });

    this.app.post('/api/tools', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const { name, kind, description, endpoint, transport, schema, scopes, enabled, ownerId, rateLimitPerMin, timeoutSeconds, metadata } = req.body || {};
        if (!name) return res.status(400).json({ error: 'name is required' });
        const tool = await this.toolRegistry.register({ name, kind, description, endpoint, transport, schema, scopes, enabled, ownerId, rateLimitPerMin, timeoutSeconds, metadata });
        res.status(201).json(tool);
      } catch (err) { next(err); }
    });

    this.app.post('/api/tools/:id/enable', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const tool = await this.toolRegistry.setEnabled(req.params.id, true);
        if (!tool) return res.status(404).json({ error: 'Tool not found' });
        res.json(tool);
      } catch (err) { next(err); }
    });

    this.app.post('/api/tools/:id/disable', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const tool = await this.toolRegistry.setEnabled(req.params.id, false);
        if (!tool) return res.status(404).json({ error: 'Tool not found' });
        res.json(tool);
      } catch (err) { next(err); }
    });

    this.app.patch('/api/tools/:id', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const tool = await this.toolRegistry.update(req.params.id, req.body || {});
        if (!tool) return res.status(404).json({ error: 'Tool not found' });
        res.json(tool);
      } catch (err) { next(err); }
    });

    this.app.post('/api/tools/:id/authorize', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const { scopes } = req.body || {};
        if (!Array.isArray(scopes)) return res.status(400).json({ error: 'scopes array is required' });
        res.json(await this.toolRegistry.authorize(req.params.id, scopes));
      } catch (err) { next(err); }
    });

    this.app.delete('/api/tools/:id', async (req: Request, res: Response, next: NextFunction) => {
      try {
        const deleted = await this.toolRegistry.delete(req.params.id);
        if (!deleted) return res.status(404).json({ error: 'Tool not found' });
        res.json({ deleted: true });
      } catch (err) { next(err); }
    });

    this.app.use((req: Request, res: Response) => {
      res.status(404).json({ error: `Not found: ${req.method} ${req.path}` });
    });

    this.app.use((err: unknown, req: Request, res: Response, next: NextFunction) => {
      const message = err instanceof Error ? err.message : 'Internal server error';
      console.error(`[api] ${req.method} ${req.path} failed:`, message);
      res.status(500).json({ error: message });
    });
  }

  private generateAuthToken(email: string): string {
    const payload = {
      email,
      iat: Math.floor(Date.now() / 1000),
      exp: Math.floor(Date.now() / 1000) + 60 * 60 * 24,
    };
    return Buffer.from(JSON.stringify(payload)).toString('base64');
  }

  public start(): Promise<void> {
    return new Promise(async (resolve, reject) => {
      try {
        await this.ensureSchema();
      } catch (err) {
        console.error('[api] Schema init failed (will retry on use):', err instanceof Error ? err.message : err);
      }
      try {
        await this.seedDefaults();
      } catch (err) {
        console.error('[api] Seed init failed (will retry on use):', err instanceof Error ? err.message : err);
      }
      this.app.listen(this.port, '0.0.0.0', () => {
        console.log(`API server started on port ${this.port}`);
        resolve();
      });
    });
  }
}

if (require.main === module) {
  const port = parseInt(process.env.PORT || '3000', 10);
  const server = new ApiServer(port);
  server.start();
}
