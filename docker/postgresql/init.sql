-- DevFoundry Database Schema
-- Run on initial database setup

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Tasks table
CREATE TABLE IF NOT EXISTS tasks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL,
  project_id UUID NOT NULL,
  user_id UUID NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'Pending',
  phase VARCHAR(20) NOT NULL DEFAULT 'Submitted',
  description TEXT NOT NULL,
  base_commit VARCHAR(64) NOT NULL,
  target_branch VARCHAR(255) NOT NULL,
  workspace_id UUID NOT NULL,
  skills JSONB NOT NULL DEFAULT '[]',
  context_ids UUID[] DEFAULT ARRAY[]::UUID[],
  memory_ids UUID[] DEFAULT ARRAY[]::UUID[],
  tool_permissions JSONB NOT NULL DEFAULT '[]',
  model_route VARCHAR(255) NOT NULL,
  capacity_profile VARCHAR(50) NOT NULL DEFAULT 'default',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  retry_count INTEGER NOT NULL DEFAULT 0,
  checkpoint JSONB,
  outcome JSONB,
  cancelled_at TIMESTAMPTZ,
  checkpoint_id UUID
);

CREATE INDEX IF NOT EXISTS idx_tasks_tenant ON tasks(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_phase ON tasks(phase);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);

-- Context nodes table
CREATE TABLE IF NOT EXISTS context_nodes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL,
  project_id UUID,
  kind VARCHAR(50) NOT NULL,
  source_id VARCHAR(255) NOT NULL,
  revision VARCHAR(64) NOT NULL,
  acl_id UUID NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_context_nodes_tenant ON context_nodes(tenant_id);
CREATE INDEX IF NOT EXISTS idx_context_nodes_project ON context_nodes(project_id);
CREATE INDEX IF NOT EXISTS idx_context_nodes_kind ON context_nodes(kind);
CREATE INDEX IF NOT EXISTS idx_context_nodes_source ON context_nodes(source_id);

-- Context edges table
CREATE TABLE IF NOT EXISTS context_edges (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID NOT NULL REFERENCES context_nodes(id) ON DELETE CASCADE,
  destination_id UUID NOT NULL REFERENCES context_nodes(id) ON DELETE CASCADE,
  relation_type VARCHAR(100) NOT NULL,
  scope VARCHAR(255) NOT NULL,
  revision VARCHAR(64) NOT NULL,
  acl_id UUID NOT NULL,
  provenance JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_context_edges_source ON context_edges(source_id);
CREATE INDEX IF NOT EXISTS idx_context_edges_destination ON context_edges(destination_id);
CREATE INDEX IF NOT EXISTS idx_context_edges_relation ON context_edges(relation_type);
CREATE INDEX IF NOT EXISTS idx_context_edges_scope ON context_edges(scope);

-- Context chunks table
CREATE TABLE IF NOT EXISTS context_chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  context_node_id UUID NOT NULL REFERENCES context_nodes(id) ON DELETE CASCADE,
  location VARCHAR(255) NOT NULL,
  revision VARCHAR(64) NOT NULL,
  text TEXT NOT NULL,
  embedding vector(768),
  embedding_model VARCHAR(100),
  embedding_version VARCHAR(50),
  full_text_indexed BOOLEAN NOT NULL DEFAULT FALSE,
  indexing_status VARCHAR(20) NOT NULL DEFAULT 'pending',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_context_chunks_node ON context_chunks(context_node_id);
CREATE INDEX IF NOT EXISTS idx_context_chunks_status ON context_chunks(indexing_status);
CREATE INDEX IF NOT EXISTS idx_context_chunks_fts ON context_chunks USING GIN (to_tsvector('english', text));

-- Memory records table
CREATE TABLE IF NOT EXISTS memory_records (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id UUID NOT NULL,
  scope VARCHAR(20) NOT NULL,
  scope_id UUID NOT NULL,
  type VARCHAR(50) NOT NULL,
  content TEXT NOT NULL,
  provenance JSONB NOT NULL DEFAULT '{}',
  revision VARCHAR(64) NOT NULL,
  ttl TIMESTAMPTZ,
  confidence DECIMAL(3, 2),
  promoted BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memory_records_owner ON memory_records(owner_id);
CREATE INDEX IF NOT EXISTS idx_memory_records_scope ON memory_records(scope, scope_id);

-- Skills table
CREATE TABLE IF NOT EXISTS skills (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  version VARCHAR(50) NOT NULL,
  digest VARCHAR(64) NOT NULL,
  name VARCHAR(255) NOT NULL,
  description TEXT,
  path VARCHAR(500) NOT NULL,
  git_repository VARCHAR(500) NOT NULL,
  git_commit VARCHAR(64) NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}',
  tests JSONB NOT NULL DEFAULT '[]',
  capability_manifest JSONB NOT NULL DEFAULT '{}',
  approval_status VARCHAR(50) NOT NULL DEFAULT 'draft',
  owner_id UUID,
  approved_at TIMESTAMPTZ,
  deprecated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(digest)
);

CREATE INDEX IF NOT EXISTS idx_skills_status ON skills(approval_status);
CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name);

-- Task outcomes table
CREATE TABLE IF NOT EXISTS task_outcomes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  attempt_id UUID NOT NULL,
  success BOOLEAN NOT NULL,
  reason TEXT,
  evidence JSONB NOT NULL DEFAULT '[]',
  trace_references JSONB NOT NULL DEFAULT '[]',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_task_outcomes_task ON task_outcomes(task_id);
CREATE INDEX IF NOT EXISTS idx_task_outcomes_attempt ON task_outcomes(attempt_id);

-- Review outcomes table
CREATE TABLE IF NOT EXISTS review_outcomes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  reviewed_by UUID NOT NULL,
  decision VARCHAR(20) NOT NULL,
  comments TEXT,
  approved_artifacts JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_review_outcomes_task ON review_outcomes(task_id);
CREATE INDEX IF NOT EXISTS idx_review_outcomes_reviewer ON review_outcomes(reviewed_by);

-- Worker status table
CREATE TABLE IF NOT EXISTS worker_status (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  worker_id VARCHAR(255) NOT NULL UNIQUE,
  hostname VARCHAR(255),
  pid INTEGER,
  status VARCHAR(20) NOT NULL DEFAULT 'idle',
  current_task_id UUID REFERENCES tasks(id),
  last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  cpu_usage DECIMAL(5, 2),
  memory_usage BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_worker_status_status ON worker_status(status);

-- Event log table for real-time streaming
CREATE TABLE IF NOT EXISTS event_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type VARCHAR(100) NOT NULL,
  entity_type VARCHAR(50) NOT NULL,
  entity_id UUID NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_event_log_type ON event_log(event_type);
CREATE INDEX IF NOT EXISTS idx_event_log_entity ON event_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_event_log_created ON event_log(created_at);

-- View for task analytics
CREATE OR REPLACE VIEW task_analytics AS
SELECT 
  t.id AS task_id,
  t.tenant_id,
  t.project_id,
  t.user_id,
  t.status,
  t.phase,
  t.retry_count,
  t.created_at,
  t.started_at,
  t.completed_at,
  EXTRACT(EPOCH FROM (t.completed_at - t.started_at)) AS duration_seconds,
  CASE 
    WHEN t.status = 'Completed' THEN TRUE
    WHEN t.status IN ('Failed', 'Cancelled') THEN FALSE
    ELSE NULL
  END AS completed_successfully,
  COUNT(to.id) OVER (PARTITION BY t.id) AS outcome_count
FROM tasks t
LEFT JOIN task_outcomes to ON t.id = to.task_id;

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
CREATE TRIGGER update_tasks_updated_at
  BEFORE UPDATE ON tasks
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_context_nodes_updated_at
  BEFORE UPDATE ON context_nodes
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_context_chunks_updated_at
  BEFORE UPDATE ON context_chunks
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_memory_records_updated_at
  BEFORE UPDATE ON memory_records
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_skills_updated_at
  BEFORE UPDATE ON skills
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_worker_status_updated_at
  BEFORE UPDATE ON worker_status
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();
