import { Database } from './database';

export interface MemoryRecord {
  id: string;
  ownerId: string;
  scope: string;
  scopeId: string;
  type: string;
  content: string;
  provenance: Record<string, unknown>;
  revision: string;
  ttl?: string;
  confidence?: number;
  promoted: boolean;
  createdAt?: string;
  updatedAt?: string;
}

export class MemoryStore {
  constructor(private db: Database) {}

  async create(record: Omit<MemoryRecord, 'id' | 'promoted'> & { id?: string; promoted?: boolean }): Promise<MemoryRecord> {
    const rows = await this.db.query(
      `INSERT INTO memory_records (id, owner_id, scope, scope_id, type, content, provenance, revision, ttl, confidence, promoted)
       VALUES (COALESCE($1, gen_random_uuid()), $2, $3, $4, $5, $6, $7, $8, $9, $10, COALESCE($11, false))
       RETURNING *`,
      [
        record.id || null,
        record.ownerId,
        record.scope,
        record.scopeId,
        record.type,
        record.content,
        JSON.stringify(record.provenance || {}),
        record.revision,
        record.ttl || null,
        record.confidence ?? null,
        record.promoted ?? false,
      ]
    );
    return this.map(rows[0]);
  }

  async get(id: string): Promise<MemoryRecord | null> {
    const rows = await this.db.query('SELECT * FROM memory_records WHERE id = $1', [id]);
    return rows.length ? this.map(rows[0]) : null;
  }

  async list(ownerId: string, opts: { scope?: string; scopeId?: string; type?: string; promotedOnly?: boolean; limit?: number } = {}): Promise<MemoryRecord[]> {
    const conditions: string[] = ['owner_id = $1'];
    const params: unknown[] = [ownerId];
    const add = (col: string, val: unknown) => {
      params.push(val);
      conditions.push(`${col} = $${params.length}`);
    };
    if (opts.scope) add('scope', opts.scope);
    if (opts.scopeId) add('scope_id::text', opts.scopeId);
    if (opts.type) add('type', opts.type);
    if (opts.promotedOnly) conditions.push('promoted = true');
    const limit = Math.min(opts.limit || 100, 500);
    const rows = await this.db.query(
      `SELECT * FROM memory_records WHERE ${conditions.join(' AND ')} ORDER BY updated_at DESC LIMIT ${limit}`,
      params
    );
    return rows.map((r) => this.map(r));
  }

  async search(ownerId: string, query: string, limit = 20): Promise<MemoryRecord[]> {
    const rows = await this.db.query(
      'SELECT * FROM memory_records WHERE owner_id = $1 AND content ILIKE $2 ORDER BY confidence DESC NULLS LAST, updated_at DESC LIMIT $3',
      [ownerId, `%${query}%`, Math.min(limit, 100)]
    );
    return rows.map((r) => this.map(r));
  }

  async update(id: string, updates: { content?: string; confidence?: number; ttl?: string | null }): Promise<MemoryRecord | null> {
    const sets: string[] = ['updated_at = NOW()'];
    const params: unknown[] = [];
    if (updates.content !== undefined) {
      params.push(updates.content);
      sets.push(`content = $${params.length}`);
    }
    if (updates.confidence !== undefined) {
      params.push(updates.confidence);
      sets.push(`confidence = $${params.length}`);
    }
    if (updates.ttl !== undefined) {
      params.push(updates.ttl);
      sets.push(`ttl = $${params.length}`);
    }
    params.push(id);
    const rows = await this.db.query(
      `UPDATE memory_records SET ${sets.join(', ')} WHERE id = $${params.length} RETURNING *`,
      params
    );
    return rows.length ? this.map(rows[0]) : null;
  }

  async promote(id: string): Promise<MemoryRecord | null> {
    const rows = await this.db.query(
      'UPDATE memory_records SET promoted = true, updated_at = NOW() WHERE id = $1 RETURNING *',
      [id]
    );
    return rows.length ? this.map(rows[0]) : null;
  }

  async delete(id: string): Promise<boolean> {
    const rows = await this.db.query('DELETE FROM memory_records WHERE id = $1 RETURNING id', [id]);
    return rows.length > 0;
  }

  async deleteExpired(): Promise<number> {
    const rows = await this.db.query(
      'DELETE FROM memory_records WHERE ttl IS NOT NULL AND ttl < NOW() RETURNING id'
    );
    return rows.length;
  }

  private map(r: Record<string, unknown>): MemoryRecord {
    return {
      id: r.id as string,
      ownerId: r.owner_id as string,
      scope: r.scope as string,
      scopeId: r.scope_id as string,
      type: r.type as string,
      content: r.content as string,
      provenance: r.provenance as Record<string, unknown>,
      revision: r.revision as string,
      ttl: (r.ttl as string) || undefined,
      confidence: r.confidence !== null && r.confidence !== undefined ? Number(r.confidence) : undefined,
      promoted: r.promoted as boolean,
      createdAt: r.created_at as string,
      updatedAt: r.updated_at as string,
    };
  }
}
