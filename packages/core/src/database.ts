import { Pool, Client } from 'pg';

export interface DatabaseConfig {
  host: string;
  port: number;
  database: string;
  username: string;
  password: string;
}

export class Database {
  public pool: Pool;

  constructor(config: DatabaseConfig) {
    this.pool = new Pool({
      host: config.host,
      port: config.port,
      database: config.database,
      user: config.username,
      password: config.password,
    });
  }

  async connect(): Promise<void> {
    await this.pool.connect();
  }

  async query<T extends {} = {}>(text: string, params?: unknown[]): Promise<T[]> {
    const result = await this.pool.query<T>(text, params);
    return result.rows;
  }

  async beginTransaction(): Promise<Client> {
    const client = await this.pool.connect();
    await client.query('BEGIN');
    return client;
  }

  async close(): Promise<void> {
    await this.pool.end();
  }
}

export async function createSchema(client: Client): Promise<void> {
  await client.query(`
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

    CREATE INDEX IF NOT EXISTS idx_tasks_tenant ON tasks(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
    CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_id);
    CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
    CREATE INDEX IF NOT EXISTS idx_tasks_phase ON tasks(phase);

    CREATE TABLE IF NOT EXISTS context_nodes (
      id UUID PRIMARY KEY,
      tenant_id UUID NOT NULL,
      project_id UUID,
      kind VARCHAR(50) NOT NULL,
      source_id VARCHAR(255) NOT NULL,
      revision VARCHAR(64) NOT NULL,
      acl_id UUID NOT NULL,
      metadata JSONB NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_context_nodes_tenant ON context_nodes(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_context_nodes_project ON context_nodes(project_id);
    CREATE INDEX IF NOT EXISTS idx_context_nodes_kind ON context_nodes(kind);
    CREATE INDEX IF NOT EXISTS idx_context_nodes_source ON context_nodes(source_id);

    CREATE TABLE IF NOT EXISTS context_edges (
      id UUID PRIMARY KEY,
      source_id UUID NOT NULL REFERENCES context_nodes(id),
      destination_id UUID NOT NULL REFERENCES context_nodes(id),
      relation_type VARCHAR(100) NOT NULL,
      scope VARCHAR(255) NOT NULL,
      revision VARCHAR(64) NOT NULL,
      acl_id UUID NOT NULL,
      provenance JSONB NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_context_edges_source ON context_edges(source_id);
    CREATE INDEX IF NOT EXISTS idx_context_edges_destination ON context_edges(destination_id);
    CREATE INDEX IF NOT EXISTS idx_context_edges_relation ON context_edges(relation_type);

    CREATE TABLE IF NOT EXISTS context_chunks (
      id UUID PRIMARY KEY,
      context_node_id UUID NOT NULL REFERENCES context_nodes(id),
      location VARCHAR(255) NOT NULL,
      revision VARCHAR(64) NOT NULL,
      text TEXT NOT NULL,
      embedding_model VARCHAR(100),
      embedding_version VARCHAR(50),
      full_text_indexed BOOLEAN NOT NULL DEFAULT FALSE,
      indexing_status VARCHAR(20) NOT NULL DEFAULT 'pending',
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_context_chunks_node ON context_chunks(context_node_id);
    CREATE INDEX IF NOT EXISTS idx_context_chunks_status ON context_chunks(indexing_status);

    CREATE TABLE IF NOT EXISTS memory_records (
      id UUID PRIMARY KEY,
      owner_id UUID NOT NULL,
      scope VARCHAR(20) NOT NULL,
      scope_id UUID NOT NULL,
      type VARCHAR(50) NOT NULL,
      content TEXT NOT NULL,
      provenance JSONB NOT NULL,
      revision VARCHAR(64) NOT NULL,
      ttl TIMESTAMPTZ,
      confidence DECIMAL(3, 2),
      promoted BOOLEAN NOT NULL DEFAULT FALSE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_memory_records_owner ON memory_records(owner_id);
    CREATE INDEX IF NOT EXISTS idx_memory_records_scope ON memory_records(scope, scope_id);

    CREATE TABLE IF NOT EXISTS skills (
      id UUID PRIMARY KEY,
      version VARCHAR(50) NOT NULL,
      digest VARCHAR(64) NOT NULL,
      name VARCHAR(255) NOT NULL,
      description TEXT,
      path VARCHAR(500) NOT NULL,
      git_repository VARCHAR(500) NOT NULL,
      git_commit VARCHAR(64) NOT NULL,
      metadata JSONB NOT NULL,
      tests JSONB NOT NULL,
      capability_manifest JSONB NOT NULL,
      approval_status VARCHAR(50) NOT NULL,
      owner_id UUID,
      approved_at TIMESTAMPTZ,
      deprecated_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_skills_status ON skills(approval_status);
    CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name);

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

    CREATE INDEX IF NOT EXISTS idx_task_outcomes_task ON task_outcomes(task_id);
  `);
}
