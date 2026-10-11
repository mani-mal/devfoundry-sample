import { Database } from './database';

export interface Skill {
  id: string;
  name: string;
  version: string;
  digest: string;
  description?: string;
  path: string;
  gitRepository: string;
  gitCommit: string;
  metadata: Record<string, unknown>;
  tests: Record<string, unknown>;
  capabilityManifest: Record<string, unknown>;
  approvalStatus: string;
  ownerId?: string;
  approvedAt?: string;
  deprecatedAt?: string;
  createdAt?: string;
  updatedAt?: string;
}

export class SkillStore {
  constructor(private db: Database) {}

  async install(skill: {
    id?: string;
    name: string;
    version?: string;
    digest?: string;
    description?: string;
    path: string;
    gitRepository: string;
    gitCommit?: string;
    metadata?: Record<string, unknown>;
    tests?: Record<string, unknown>;
    capabilityManifest?: Record<string, unknown>;
    approvalStatus?: string;
    ownerId?: string;
  }): Promise<Skill> {
    const rows = await this.db.query(
      `INSERT INTO skills (id, name, version, digest, description, path, git_repository, git_commit, metadata, tests, capability_manifest, approval_status, owner_id)
       VALUES (COALESCE($1, gen_random_uuid()), $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
       RETURNING *`,
      [
        skill.id || null,
        skill.name,
        skill.version || '1.0.0',
        skill.digest || this.computeDigest(skill),
        skill.description || null,
        skill.path,
        skill.gitRepository,
        skill.gitCommit || 'HEAD',
        JSON.stringify(skill.metadata || {}),
        JSON.stringify(skill.tests || {}),
        JSON.stringify(skill.capabilityManifest || {}),
        skill.approvalStatus || 'draft',
        skill.ownerId || null,
      ]
    );
    return this.map(rows[0]);
  }

  async get(id: string): Promise<Skill | null> {
    const rows = await this.db.query('SELECT * FROM skills WHERE id = $1', [id]);
    return rows.length ? this.map(rows[0]) : null;
  }

  async list(opts: { status?: string; limit?: number } = {}): Promise<Skill[]> {
    const conditions: string[] = [];
    const params: unknown[] = [];
    if (opts.status) {
      params.push(opts.status);
      conditions.push(`approval_status = $${params.length}`);
    }
    const where = conditions.length ? `WHERE ${conditions.join(' AND ')}` : '';
    const limit = Math.min(opts.limit || 100, 500);
    const rows = await this.db.query(
      `SELECT * FROM skills ${where} ORDER BY name, version LIMIT ${limit}`,
      params
    );
    return rows.map((r) => this.map(r));
  }

  async findByName(name: string, opts: { version?: string } = {}): Promise<Skill | null> {
    const params: unknown[] = [name];
    let sql = 'SELECT * FROM skills WHERE name = $1';
    if (opts.version) {
      params.push(opts.version);
      sql += ' AND version = $2';
    }
    sql += ' ORDER BY created_at DESC LIMIT 1';
    const rows = await this.db.query(sql, params);
    return rows.length ? this.map(rows[0]) : null;
  }

  async updateStatus(id: string, status: string): Promise<Skill | null> {
    const valid = ['draft', 'linted', 'sandbox-tested', 'evaluated', 'approved', 'published', 'deprecated'];
    if (!valid.includes(status)) {
      throw new Error(`Invalid approval status: ${status}. Valid: ${valid.join(', ')}`);
    }
    const extras =
      status === 'approved'
        ? ', approved_at = NOW()'
        : status === 'deprecated'
          ? ', deprecated_at = NOW()'
          : '';
    const rows = await this.db.query(
      `UPDATE skills SET approval_status = $1${extras}, updated_at = NOW() WHERE id = $2 RETURNING *`,
      [status, id]
    );
    return rows.length ? this.map(rows[0]) : null;
  }

  async approveByDigest(digest: string): Promise<Skill | null> {
    const rows = await this.db.query(
      `UPDATE skills SET approval_status = 'approved', approved_at = NOW(), updated_at = NOW()
       WHERE digest = $1 RETURNING *`,
      [digest]
    );
    return rows.length ? this.map(rows[0]) : null;
  }

  async rollbackToDigest(digest: string): Promise<Skill | null> {
    const rows = await this.db.query(
      `UPDATE skills SET approval_status = 'approved', deprecated_at = NULL, updated_at = NOW()
       WHERE digest = $1 RETURNING *`,
      [digest]
    );
    return rows.length ? this.map(rows[0]) : null;
  }

  async deprecate(id: string): Promise<Skill | null> {
    return this.updateStatus(id, 'deprecated');
  }

  async delete(id: string): Promise<boolean> {
    const rows = await this.db.query('DELETE FROM skills WHERE id = $1 RETURNING id', [id]);
    return rows.length > 0;
  }

  private computeDigest(skill: { name: string; version?: string; path: string; gitRepository: string; gitCommit?: string }): string {
    // Deterministic digest of the skill identity; replaced by content hash at publish time.
    const crypto = require('crypto') as typeof import('crypto');
    const parts = [skill.name, skill.version || '1.0.0', skill.path, skill.gitRepository, skill.gitCommit || 'HEAD'];
    return crypto.createHash('sha256').update(parts.join('\x1f')).digest('hex');
  }

  private map(r: Record<string, unknown>): Skill {
    return {
      id: r.id as string,
      name: r.name as string,
      version: r.version as string,
      digest: r.digest as string,
      description: (r.description as string) || undefined,
      path: r.path as string,
      gitRepository: r.git_repository as string,
      gitCommit: r.git_commit as string,
      metadata: r.metadata as Record<string, unknown>,
      tests: r.tests as Record<string, unknown>,
      capabilityManifest: r.capability_manifest as Record<string, unknown>,
      approvalStatus: r.approval_status as string,
      ownerId: (r.owner_id as string) || undefined,
      approvedAt: r.approved_at as string,
      deprecatedAt: r.deprecated_at as string,
      createdAt: r.created_at as string,
      updatedAt: r.updated_at as string,
    };
  }
}
