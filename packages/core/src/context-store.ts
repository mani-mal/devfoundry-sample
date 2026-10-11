import { Database } from './database';

export interface ContextNode {
  id: string;
  tenantId: string;
  projectId?: string;
  kind: string;
  sourceId: string;
  revision: string;
  aclId: string;
  metadata: Record<string, unknown>;
  createdAt?: string;
  updatedAt?: string;
}

export interface ContextEdge {
  id: string;
  sourceId: string;
  destinationId: string;
  relationType: string;
  scope: string;
  revision: string;
  aclId: string;
  provenance: Record<string, unknown>;
}

export interface ContextChunk {
  id: string;
  contextNodeId: string;
  location: string;
  revision: string;
  text: string;
  embeddingModel?: string;
  embeddingVersion?: string;
  fullTextIndexed: boolean;
  indexingStatus: string;
}

export class ContextStore {
  constructor(private db: Database) {}

  async createNode(node: Omit<ContextNode, 'id'> & { id?: string }): Promise<ContextNode> {
    const rows = await this.db.query(
      `INSERT INTO context_nodes (id, tenant_id, project_id, kind, source_id, revision, acl_id, metadata)
       VALUES (COALESCE($1, gen_random_uuid()), $2, $3, $4, $5, $6, $7, $8)
       RETURNING *`,
      [
        node.id || null,
        node.tenantId,
        node.projectId || null,
        node.kind,
        node.sourceId,
        node.revision,
        node.aclId,
        JSON.stringify(node.metadata || {}),
      ]
    );
    return this.mapNode(rows[0]);
  }

  async getNode(id: string): Promise<ContextNode | null> {
    const rows = await this.db.query('SELECT * FROM context_nodes WHERE id = $1', [id]);
    return rows.length ? this.mapNode(rows[0]) : null;
  }

  async findNodeBySource(tenantId: string, sourceId: string): Promise<ContextNode | null> {
    const rows = await this.db.query(
      'SELECT * FROM context_nodes WHERE tenant_id = $1 AND source_id = $2 ORDER BY created_at DESC LIMIT 1',
      [tenantId, sourceId]
    );
    return rows.length ? this.mapNode(rows[0]) : null;
  }

  async listNodes(tenantId: string, opts: { kind?: string; projectId?: string; limit?: number } = {}): Promise<ContextNode[]> {
    const conditions: string[] = ['tenant_id = $1'];
    const params: unknown[] = [tenantId];
    if (opts.kind) {
      params.push(opts.kind);
      conditions.push(`kind = $${params.length}`);
    }
    if (opts.projectId) {
      params.push(opts.projectId);
      conditions.push(`project_id = $${params.length}`);
    }
    const limit = Math.min(opts.limit || 100, 500);
    const rows = await this.db.query(
      `SELECT * FROM context_nodes WHERE ${conditions.join(' AND ')} ORDER BY updated_at DESC LIMIT ${limit}`,
      params
    );
    return rows.map((r) => this.mapNode(r));
  }

  async createEdge(edge: Omit<ContextEdge, 'id'> & { id?: string }): Promise<ContextEdge> {
    const rows = await this.db.query(
      `INSERT INTO context_edges (id, source_id, destination_id, relation_type, scope, revision, acl_id, provenance)
       VALUES (COALESCE($1, gen_random_uuid()), $2, $3, $4, $5, $6, $7, $8)
       RETURNING *`,
      [
        edge.id || null,
        edge.sourceId,
        edge.destinationId,
        edge.relationType,
        edge.scope,
        edge.revision,
        edge.aclId,
        JSON.stringify(edge.provenance || {}),
      ]
    );
    return this.mapEdge(rows[0]);
  }

  async listEdges(tenantId: string, opts: { nodeId?: string; relationType?: string; limit?: number } = {}): Promise<ContextEdge[]> {
    const conditions: string[] = [];
    const params: unknown[] = [];
    if (opts.nodeId) {
      params.push(opts.nodeId);
      conditions.push(`(source_id = $${params.length} OR destination_id = $${params.length})`);
    }
    if (opts.relationType) {
      params.push(opts.relationType);
      conditions.push(`relation_type = $${params.length}`);
    }
    const limit = Math.min(opts.limit || 100, 500);
    const where = conditions.length ? `WHERE ${conditions.join(' AND ')}` : '';
    const rows = await this.db.query(
      `SELECT * FROM context_edges ${where} ORDER BY created_at DESC LIMIT ${limit}`,
      params
    );
    return rows.map((r) => this.mapEdge(r));
  }

  async addChunk(chunk: Omit<ContextChunk, 'id' | 'fullTextIndexed' | 'indexingStatus'> & { id?: string }): Promise<ContextChunk> {
    const rows = await this.db.query(
      `INSERT INTO context_chunks (id, context_node_id, location, revision, text, embedding_model, embedding_version, full_text_indexed, indexing_status)
       VALUES (COALESCE($1, gen_random_uuid()), $2, $3, $4, $5, $6, $7, true, 'indexed')
       RETURNING *`,
      [
        chunk.id || null,
        chunk.contextNodeId,
        chunk.location,
        chunk.revision,
        chunk.text,
        chunk.embeddingModel || null,
        chunk.embeddingVersion || null,
      ]
    );
    return this.mapChunk(rows[0]);
  }

  async listChunks(nodeId: string, limit = 50): Promise<ContextChunk[]> {
    const rows = await this.db.query(
      'SELECT * FROM context_chunks WHERE context_node_id = $1 ORDER BY created_at DESC LIMIT $2',
      [nodeId, Math.min(limit, 200)]
    );
    return rows.map((r) => this.mapChunk(r));
  }

  async searchChunks(tenantId: string, query: string, limit = 20): Promise<(ContextChunk & { node?: ContextNode })[]> {
    const rows = await this.db.query(
      `SELECT c.*, n.kind AS node_kind, n.source_id AS node_source_id, n.metadata AS node_metadata
       FROM context_chunks c
       JOIN context_nodes n ON n.id = c.context_node_id
       WHERE n.tenant_id = $1
         AND c.text ILIKE $2
       ORDER BY c.updated_at DESC
       LIMIT $3`,
      [tenantId, `%${query}%`, Math.min(limit, 100)]
    );
    return rows.map((r: Record<string, unknown>) => ({
      ...this.mapChunk(r),
      node: {
        id: r.node_source_id,
        kind: r.node_kind,
        metadata: r.node_metadata,
      } as unknown as ContextNode,
    }));
  }

  async traverse(
    tenantId: string,
    startNodeId: string,
    opts: { maxHops?: number; relationType?: string; limit?: number } = {}
  ): Promise<{ nodes: ContextNode[]; edges: ContextEdge[] }> {
    const maxHops = Math.min(opts.maxHops || 2, 4);
    const limit = Math.min(opts.limit || 50, 200);
    const relFilter = opts.relationType
      ? `AND e.relation_type = ${JSON.stringify(opts.relationType).replace(/'/g, "''")}`
      : '';
    const rows = await this.db.query(
      `WITH RECURSIVE walk AS (
         SELECT n.id, n.tenant_id, 0 AS depth, ARRAY[n.id] AS path
         FROM context_nodes n
         WHERE n.id = $1 AND n.tenant_id = $2
         UNION ALL
         SELECT n.id, n.tenant_id, w.depth + 1, w.path || n.id
         FROM walk w
         JOIN context_edges e ON (e.source_id = w.id OR e.destination_id = w.id) ${relFilter}
         JOIN context_nodes n ON n.id = CASE WHEN e.source_id = w.id THEN e.destination_id ELSE e.source_id END
         WHERE w.depth < $3 AND NOT n.id = ANY(w.path)
       )
       SELECT DISTINCT n.* FROM walk JOIN context_nodes n ON n.id = walk.id
       LIMIT $4`,
      [startNodeId, tenantId, maxHops, limit]
    );
    const nodes = rows.map((r) => this.mapNode(r));
    const nodeIds = nodes.map((n) => n.id);
    let edges: ContextEdge[] = [];
    if (nodeIds.length) {
      const edgeRows = await this.db.query(
        `SELECT * FROM context_edges WHERE source_id = ANY($1::uuid[]) AND destination_id = ANY($1::uuid[]) LIMIT $2`,
        [nodeIds, limit]
      );
      edges = edgeRows.map((r) => this.mapEdge(r));
    }
    return { nodes, edges };
  }

  async stats(tenantId: string): Promise<{ nodes: number; edges: number; chunks: number }> {
    const nodes = (await this.db.query('SELECT COUNT(*)::int AS c FROM context_nodes WHERE tenant_id = $1', [tenantId])) as Array<{ c: number }>;
    const edges = (await this.db.query(
      'SELECT COUNT(*)::int AS c FROM context_edges e JOIN context_nodes n ON n.id = e.source_id WHERE n.tenant_id = $1',
      [tenantId]
    )) as Array<{ c: number }>;
    const chunks = (await this.db.query(
      'SELECT COUNT(*)::int AS c FROM context_chunks c JOIN context_nodes n ON n.id = c.context_node_id WHERE n.tenant_id = $1',
      [tenantId]
    )) as Array<{ c: number }>;
    return {
      nodes: nodes[0]?.c ?? 0,
      edges: edges[0]?.c ?? 0,
      chunks: chunks[0]?.c ?? 0,
    };
  }

  private mapNode(r: Record<string, unknown>): ContextNode {
    return {
      id: r.id as string,
      tenantId: r.tenant_id as string,
      projectId: (r.project_id as string) || undefined,
      kind: r.kind as string,
      sourceId: r.source_id as string,
      revision: r.revision as string,
      aclId: r.acl_id as string,
      metadata: r.metadata as Record<string, unknown>,
      createdAt: r.created_at as string,
      updatedAt: r.updated_at as string,
    };
  }

  private mapEdge(r: Record<string, unknown>): ContextEdge {
    return {
      id: r.id as string,
      sourceId: r.source_id as string,
      destinationId: r.destination_id as string,
      relationType: r.relation_type as string,
      scope: r.scope as string,
      revision: r.revision as string,
      aclId: r.acl_id as string,
      provenance: r.provenance as Record<string, unknown>,
    };
  }

  private mapChunk(r: Record<string, unknown>): ContextChunk {
    return {
      id: r.id as string,
      contextNodeId: r.context_node_id as string,
      location: r.location as string,
      revision: r.revision as string,
      text: r.text as string,
      embeddingModel: (r.embedding_model as string) || undefined,
      embeddingVersion: (r.embedding_version as string) || undefined,
      fullTextIndexed: r.full_text_indexed as boolean,
      indexingStatus: r.indexing_status as string,
    };
  }
}
