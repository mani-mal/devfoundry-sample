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
  toolPermissions: ToolPermission[];
  modelRoute: string;
  capacityProfile: string;
  createdAt: string;
  updatedAt: string;
  startedAt?: string;
  completedAt?: string;
  retryCount: number;
  checkpoint?: TaskCheckpoint;
  outcome?: TaskOutcome;
}

export interface ToolPermission {
  toolId: string;
  scopes: string[];
  readOnly: boolean;
}

export interface TaskCheckpoint {
  snapshotId: string;
  workspaceState: WorkspaceState;
  sessionState: SessionState;
  timestamp: string;
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

export interface TaskOutcome {
  success: boolean;
  reason?: string;
  evidence: EvidenceItem[];
  traceReferences: TraceReference[];
}

export interface EvidenceItem {
  type: 'file' | 'command' | 'test' | 'lint' | 'security' | 'ui' | 'model';
  content: string;
  timestamp: string;
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
