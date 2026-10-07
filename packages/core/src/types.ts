export type TaskPhase = 
  | 'Submitted' 
  | 'Qualified' 
  | 'Running' 
  | 'Validating' 
  | 'AwaitingReview' 
  | 'Completed' 
  | 'Failed' 
  | 'Cancelled' 
  | 'Paused';

export type TaskStatus = 
  | 'Pending' 
  | 'InProgress' 
  | 'Completed' 
  | 'Failed' 
  | 'Cancelled';

export type IdentityType = 'user' | 'task' | 'service';

export interface Identity {
  id: string;
  type: IdentityType;
  tenantId: string;
  projectId?: string;
  scopes: string[];
  credentials: {
    token?: string;
    service?: string;
    spiiffe?: string;
  };
}

export interface Task {
  id: string;
  tenantId: string;
  projectId: string;
  userId: string;
  status: TaskStatus;
  phase: TaskPhase;
  description: string;
  baseCommit: string;
  targetBranch: string;
  workspaceId: string;
  skills: string[];
  contextIds: string[];
  memoryIds: string[];
  toolPermissions: ToolPermission[];
  modelRoute: string;
  capacityProfile: string;
  createdAt: Date;
  updatedAt: Date;
  startedAt?: Date;
  completedAt?: Date;
  retryCount: number;
  checkpoint?: TaskCheckpoint;
  outcome?: TaskOutcome;
}

export interface TaskCheckpoint {
  snapshotId: string;
  workspaceState: WorkspaceState;
  sessionState: SessionState;
  timestamp: Date;
}

export interface TaskOutcome {
  success: boolean;
  reason?: string;
  evidence: EvidenceItem[];
  traceReferences: TraceReference[];
}

export interface EvidenceItem {
  type: 'file' | 'command' | 'test' | 'lint' | 'security' | 'ui' | 'model';
  content: string;
  timestamp: Date;
  provenance: {
    skillId?: string;
    toolId?: string;
    phase: TaskPhase;
  };
}

export interface TraceReference {
  traceId: string;
  spanId?: string;
  gateway: string;
  taskId: string;
  attemptId: string;
  phase: TaskPhase;
}

export interface ToolPermission {
  toolId: string;
  scopes: string[];
  readOnly: boolean;
}

export interface WorkspaceState {
  worktreePath: string;
  baseCommit: string;
  isDirty: boolean;
  fileChanges: FileChange[];
}

export interface FileChange {
  path: string;
  status: 'added' | 'modified' | 'deleted';
  diff?: string;
}

export interface SessionState {
  sessionId: string;
  harness: string;
  lastEventId?: string;
}

export interface Skill {
  id: string;
  version: string;
  digest: string;
  name: string;
  description: string;
  path: string;
  gitRepository: string;
  gitCommit: string;
  metadata: SkillMetadata;
  tests: SkillTest[];
  capabilityManifest: CapabilityManifest;
  approvalStatus: SkillApprovalStatus;
  ownerId?: string;
  approvedAt?: Date;
  deprecatedAt?: Date;
}

export interface SkillMetadata {
  type: 'core' | 'domain';
  languages: string[];
  requiredCapabilities: string[];
  recommendedModels: string[];
  tests: SkillTest[];
}

export interface SkillTest {
  name: string;
  description: string;
  input: string;
  expectedOutput: string;
  pass: boolean;
}

export interface CapabilityManifest {
  tools: string[];
  gitOperations: boolean;
  writeCapabilities: boolean;
}

export type SkillApprovalStatus = 'draft' | 'linted' | 'sandbox-tested' | 'evaluated' | 'approved' | 'published' | 'deprecated';

export interface ContextNode {
  id: string;
  tenantId: string;
  projectId?: string;
  kind: 'repo' | 'service' | 'document' | 'issue' | 'pr' | 'dependency' | 'symbol';
  sourceId: string;
  revision: string;
  aclId: string;
  metadata: Record<string, unknown>;
  createdAt: Date;
  updatedAt: Date;
}

export interface ContextEdge {
  id: string;
  sourceId: string;
  destinationId: string;
  relationType: string;
  scope: string;
  revision: string;
  aclId: string;
  provenance: {
    source: string;
    timestamp: Date;
  };
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
  createdAt: Date;
  updatedAt: Date;
  indexingStatus: 'pending' | 'processing' | 'completed' | 'failed';
}

export interface MemoryRecord {
  id: string;
  ownerId: string;
  scope: 'user' | 'project' | 'task';
  scopeId: string;
  type: 'preference' | 'convention' | 'summary' | 'lesson';
  content: string;
  provenance: {
    source: string;
    sourceId?: string;
  };
  revision: string;
  ttl?: Date;
  confidence?: number;
  promoted: boolean;
  createdAt: Date;
  updatedAt: Date;
}

export interface HardwareProfile {
  name: string;
  cpu: {
    cores: number;
    ram: number;
    disk: number;
  };
  gpu?: {
    type: string;
    count: number;
    vram: number;
  };
  compatibleModels: string[];
  default: boolean;
}

export interface CapacityAdmission {
  taskId: string;
  cpuRequired: number;
  ramRequired: number;
  gpuRequired?: number;
  gpuMemoryRequired?: number;
  estimatedKVCache: number;
  priority: number;
  queueTime: number;
}
