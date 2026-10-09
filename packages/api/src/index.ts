import express, { Request, Response, NextFunction } from 'express';
import { Pool } from 'pg';
import { v4 as uuidv4 } from 'uuid';
import os from 'os';

export class ApiServer {
  private app: express.Express;
  private port: number;
  private pool: Pool;
  private startTime = Date.now();

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
      const total = os.totalmem();
      const free = os.freemem();
      res.json({
        status: 'ok',
        uptime: Math.floor((Date.now() - this.startTime) / 1000),
        services: {
          api: { status: 'ok', uptime: Math.floor((Date.now() - this.startTime) / 1000) },
          database: { status: dbStatus },
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
