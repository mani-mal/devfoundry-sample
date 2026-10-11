import { Database } from './database';

export interface ApprovedTool {
  id: string;
  name: string;
  kind: string;
  description?: string;
  endpoint?: string;
  transport?: string;
  schema: Record<string, unknown>;
  scopes: string[];
  enabled: boolean;
  ownerId?: string;
  approvedAt?: string;
  rateLimitPerMin?: number;
  timeoutSeconds?: number;
  metadata: Record<string, unknown>;
  createdAt?: string;
  updatedAt?: string;
}

export class ToolRegistry {
  constructor(private db: Database) {}

  private async ensureTable(): Promise<void> {
    await this.db.query(`
      CREATE TABLE IF NOT EXISTS approved_tools (
        id UUID PRIMARY KEY,
        name VARCHAR(255) NOT NULL UNIQUE,
        kind VARCHAR(50) NOT NULL DEFAULT 'tool',
        description TEXT,
        endpoint VARCHAR(500),
        transport VARCHAR(50) DEFAULT 'http',
        schema JSONB NOT NULL DEFAULT '{}'::jsonb,
        scopes JSONB NOT NULL DEFAULT '[]'::jsonb,
        enabled BOOLEAN NOT NULL DEFAULT FALSE,
        owner_id UUID,
        approved_at TIMESTAMPTZ,
        rate_limit_per_min INTEGER DEFAULT 60,
        timeout_seconds INTEGER DEFAULT 30,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
      );
      CREATE INDEX IF NOT EXISTS idx_approved_tools_enabled ON approved_tools(enabled);
    `);
  }

  async register(tool: {
    id?: string;
    name: string;
    kind?: string;
    description?: string;
    endpoint?: string;
    transport?: string;
    schema?: Record<string, unknown>;
    scopes?: string[];
    enabled?: boolean;
    ownerId?: string;
    rateLimitPerMin?: number;
    timeoutSeconds?: number;
    metadata?: Record<string, unknown>;
  }): Promise<ApprovedTool> {
    await this.ensureTable();
    const rows = await this.db.query(
      `INSERT INTO approved_tools (id, name, kind, description, endpoint, transport, schema, scopes, enabled, owner_id, approved_at, rate_limit_per_min, timeout_seconds, metadata)
       VALUES (COALESCE($1, gen_random_uuid()), $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
       ON CONFLICT (name) DO UPDATE SET
         kind = EXCLUDED.kind,
         description = EXCLUDED.description,
         endpoint = EXCLUDED.endpoint,
         transport = EXCLUDED.transport,
         schema = EXCLUDED.schema,
         scopes = EXCLUDED.scopes,
         updated_at = NOW()
       RETURNING *`,
      [
        tool.id || null,
        tool.name,
        tool.kind || 'tool',
        tool.description || null,
        tool.endpoint || null,
        tool.transport || 'http',
        JSON.stringify(tool.schema || {}),
        JSON.stringify(tool.scopes || []),
        tool.enabled ?? false,
        tool.ownerId || null,
        tool.enabled ? new Date().toISOString() : null,
        tool.rateLimitPerMin ?? 60,
        tool.timeoutSeconds ?? 30,
        JSON.stringify(tool.metadata || {}),
      ]
    );
    return this.map(rows[0]);
  }

  async get(id: string): Promise<ApprovedTool | null> {
    await this.ensureTable();
    const rows = await this.db.query('SELECT * FROM approved_tools WHERE id = $1', [id]);
    return rows.length ? this.map(rows[0]) : null;
  }

  async findByName(name: string): Promise<ApprovedTool | null> {
    await this.ensureTable();
    const rows = await this.db.query('SELECT * FROM approved_tools WHERE name = $1', [name]);
    return rows.length ? this.map(rows[0]) : null;
  }

  async list(opts: { enabledOnly?: boolean; kind?: string; limit?: number } = {}): Promise<ApprovedTool[]> {
    await this.ensureTable();
    const conditions: string[] = [];
    const params: unknown[] = [];
    if (opts.enabledOnly) conditions.push('enabled = true');
    if (opts.kind) {
      params.push(opts.kind);
      conditions.push(`kind = $${params.length}`);
    }
    const where = conditions.length ? `WHERE ${conditions.join(' AND ')}` : '';
    const limit = Math.min(opts.limit || 100, 500);
    const rows = await this.db.query(
      `SELECT * FROM approved_tools ${where} ORDER BY name LIMIT ${limit}`,
      params
    );
    return rows.map((r) => this.map(r));
  }

  async search(query: string, opts: { enabledOnly?: boolean; limit?: number } = {}): Promise<ApprovedTool[]> {
    await this.ensureTable();
    const enabledFilter = opts.enabledOnly ? 'AND enabled = true' : '';
    const limit = Math.min(opts.limit || 50, 200);
    const rows = await this.db.query(
      `SELECT * FROM approved_tools WHERE (name ILIKE $1 OR description ILIKE $1) ${enabledFilter} ORDER BY name LIMIT $2`,
      [`%${query}%`, limit]
    );
    return rows.map((r) => this.map(r));
  }

  async setEnabled(id: string, enabled: boolean): Promise<ApprovedTool | null> {
    await this.ensureTable();
    const rows = await this.db.query(
      `UPDATE approved_tools SET enabled = $1, approved_at = CASE WHEN $1 THEN NOW() ELSE approved_at END, updated_at = NOW()
       WHERE id = $2 RETURNING *`,
      [enabled, id]
    );
    return rows.length ? this.map(rows[0]) : null;
  }

  async update(id: string, updates: { description?: string; scopes?: string[]; rateLimitPerMin?: number; timeoutSeconds?: number; endpoint?: string }): Promise<ApprovedTool | null> {
    await this.ensureTable();
    const sets: string[] = ['updated_at = NOW()'];
    const params: unknown[] = [];
    const add = (col: string, val: unknown, json = false) => {
      params.push(json ? JSON.stringify(val) : val);
      sets.push(`${col} = $${params.length}`);
    };
    if (updates.description !== undefined) add('description', updates.description);
    if (updates.scopes !== undefined) add('scopes', updates.scopes, true);
    if (updates.rateLimitPerMin !== undefined) add('rate_limit_per_min', updates.rateLimitPerMin);
    if (updates.timeoutSeconds !== undefined) add('timeout_seconds', updates.timeoutSeconds);
    if (updates.endpoint !== undefined) add('endpoint', updates.endpoint);
    params.push(id);
    const rows = await this.db.query(
      `UPDATE approved_tools SET ${sets.join(', ')} WHERE id = $${params.length} RETURNING *`,
      params
    );
    return rows.length ? this.map(rows[0]) : null;
  }

  async authorize(id: string, requestedScopes: string[]): Promise<{ allowed: boolean; missing: string[] }> {
    const tool = await this.get(id);
    if (!tool) return { allowed: false, missing: ['tool-not-found'] };
    if (!tool.enabled) return { allowed: false, missing: ['tool-disabled'] };
    const missing = requestedScopes.filter((s) => !tool.scopes.includes(s));
    return { allowed: missing.length === 0, missing };
  }

  async delete(id: string): Promise<boolean> {
    await this.ensureTable();
    const rows = await this.db.query('DELETE FROM approved_tools WHERE id = $1 RETURNING id', [id]);
    return rows.length > 0;
  }

  private map(r: Record<string, unknown>): ApprovedTool {
    return {
      id: r.id as string,
      name: r.name as string,
      kind: r.kind as string,
      description: (r.description as string) || undefined,
      endpoint: (r.endpoint as string) || undefined,
      transport: (r.transport as string) || 'http',
      schema: r.schema as Record<string, unknown>,
      scopes: (r.scopes as string[]) || [],
      enabled: r.enabled as boolean,
      ownerId: (r.owner_id as string) || undefined,
      approvedAt: r.approved_at as string,
      rateLimitPerMin: (r.rate_limit_per_min as number) ?? 60,
      timeoutSeconds: (r.timeout_seconds as number) ?? 30,
      metadata: r.metadata as Record<string, unknown>,
      createdAt: r.created_at as string,
      updatedAt: r.updated_at as string,
    };
  }
}
