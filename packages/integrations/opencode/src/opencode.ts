/**
 * OpenCode Adapter for DevFoundry
 *
 * Integrates with OpenCode (agent framework) via its HTTP API:
 *   POST /session                      -> create session
 *   GET  /session                      -> list sessions
 *   GET  /session/:id                  -> get session (returns array)
 *   POST /session/:id/message          -> send text message
 *   POST /session/:id/shell            -> run shell command (agent required)
 *   POST /session/:id/abort            -> cancel/abort session
 *
 * DevFoundry uses OpenCode as a managed harness/worker through its HTTP API.
 */

import axios, { AxiosInstance } from 'axios';

export interface OpenCodeConfig {
  baseUrl: string;
  apiKey?: string;
  timeout?: number;
}

export interface OpenCodeSession {
  id: string;
  slug?: string;
  projectID?: string;
  directory?: string;
  title?: string;
  cost?: number;
  createdAt?: string;
  updatedAt?: string;
  [key: string]: unknown;
}

export interface OpenCodeEvent {
  id: string;
  type: string;
  timestamp: string;
  payload: Record<string, unknown>;
}

export interface OpenCodeWorkspace {
  id: string;
  status: 'pending' | 'ready' | 'failed';
  worktreePath?: string;
  baseCommit?: string;
  environment?: Record<string, string>;
  createdAt: string;
}

export interface OpenCodeTaskRequest {
  task: string;
  instructions?: string;
  tools?: string[];
  context?: Record<string, unknown>;
  workspaceId?: string;
  checkpointId?: string;
}

export interface OpenCodeFileChange {
  path: string;
  status: 'added' | 'modified' | 'deleted';
}

export interface OpenCodeCheckpoint {
  id: string;
  sessionId: string;
  snapshotId: string;
  workspaceState: {
    worktreePath: string;
    baseCommit: string;
    isDirty: boolean;
    fileChanges: OpenCodeFileChange[];
  };
  sessionState: {
    sessionId: string;
    lastEventId?: string;
  };
  timestamp: string;
}

/** Strip a { name, data } error envelope and surface a readable message. */
function unwrapError(error: unknown, fallback: string): Error {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as { name?: string; data?: { message?: string } } | string | undefined;
    if (typeof data === 'object' && data !== null && typeof data.data === 'object' && data.data?.message) {
      return new Error(`${fallback}: ${data.data.message}`);
    }
    return new Error(`${fallback}: ${(error as Error).message}`);
  }
  return new Error(`${fallback}: ${(error as Error).message}`);
}

export class OpenCodeAdapter {
  private client: AxiosInstance;
  private config: OpenCodeConfig;

  constructor(config: OpenCodeConfig) {
    this.config = config;
    this.client = axios.create({
      baseURL: config.baseUrl,
      timeout: config.timeout || 60000,
      headers: config.apiKey ? { Authorization: `Bearer ${config.apiKey}` } : {},
      proxy: false,
    });
  }

  /**
   * Health check - verify OpenCode is running (GET / returns the SPA).
   */
  async healthCheck(): Promise<boolean> {
    try {
      const response = await this.client.get('/');
      return response.status === 200;
    } catch {
      return false;
    }
  }

  /**
   * Create a new agent session (POST /session).
   */
  async createSession(request: OpenCodeTaskRequest): Promise<OpenCodeSession> {
    try {
      const body: Record<string, unknown> = {};
      if (request.task) {
        body.title = request.task;
      }
      const response = await this.client.post<OpenCodeSession>('/session', body);
      return response.data;
    } catch (error) {
      throw unwrapError(error, 'OpenCode session creation error');
    }
  }

  /**
   * List sessions (GET /session).
   */
  async listSessions(): Promise<OpenCodeSession[]> {
    try {
      const response = await this.client.get<OpenCodeSession[]>('/session');
      return response.data;
    } catch (error) {
      throw unwrapError(error, 'OpenCode list sessions error');
    }
  }

  /**
   * Send text input to a session (POST /session/:id/message).
   */
  async sendInput(sessionId: string, input: string): Promise<OpenCodeEvent[]> {
    try {
      const response = await this.client.post(
        `/session/${sessionId}/message`,
        {
          parts: [{ type: 'text', text: input }],
        },
        { timeout: this.config.timeout || 120000 }
      );
      const data = response.data;
      // The reply is the assistant message: { info, parts }
      return Array.isArray(data)
        ? data
        : [{
            id: (data as { info?: { id?: string } })?.info?.id ?? 'reply',
            type: 'message',
            timestamp: new Date().toISOString(),
            payload: data as Record<string, unknown>,
          }];
    } catch (error) {
      throw unwrapError(error, 'OpenCode send input error');
    }
  }

  /**
   * Run a shell command inside the session (POST /session/:id/shell).
   * Returns the tool part output, or empty string if unavailable.
   */
  async runShellCommand(sessionId: string, command: string): Promise<{ status: string; output: string }> {
    try {
      const response = await this.client.post(
        `/session/${sessionId}/shell`,
        { agent: 'build', command },
        { timeout: this.config.timeout || 120000 }
      );
      const parts = (response.data as { parts?: Array<Record<string, unknown>> }).parts ?? [];
      for (const p of parts) {
        if ((p as Record<string, unknown>).type === 'tool') {
          const state = (p as Record<string, unknown>).state as
            | { status?: string; output?: string }
            | undefined;
          return {
            status: state?.status ?? 'unknown',
            output: typeof state?.output === 'string' ? state.output : '',
          };
        }
      }
      return { status: 'unknown', output: '' };
    } catch (error) {
      throw unwrapError(error, 'OpenCode shell command error');
    }
  }

  /**
   * Collect file changes from the session's working directory via git.
   */
  async collectFileChanges(sessionId: string, repoPath: string): Promise<OpenCodeFileChange[]> {
    try {
      const result = await this.runShellCommand(
        sessionId,
        'git status --porcelain && git diff --numstat'
      );
      if (result.status !== 'completed' || !result.output) {
        return [];
      }
      return parseGitPorcelain(result.output);
    } catch {
      return [];
    }
  }

  /**
   * Cancel/abort a session (POST /session/:id/abort).
   */
  async cancelSession(sessionId: string): Promise<void> {
    try {
      await this.client.post(`/session/${sessionId}/abort`);
    } catch (error) {
      throw unwrapError(error, 'OpenCode cancel session error');
    }
  }

  /**
   * Create a workspace — maps to a session working in the repo directory.
   * OpenCode sessions are directory-scoped, so we create a session and report
   * its directory as the worktree path.
   */
  async createWorkspace(config: {
    baseCommit: string;
    environment?: Record<string, string>;
    resourceLimits?: {
      cpu?: number;
      memory?: string;
    };
  }): Promise<OpenCodeWorkspace> {
    try {
      const session = await this.createSession({ task: `workspace-${config.baseCommit}` });
      return {
        id: session.id,
        status: 'ready',
        worktreePath: (session.directory as string) ?? '/app',
        baseCommit: config.baseCommit,
        environment: config.environment,
        createdAt: new Date().toISOString(),
      };
    } catch (error) {
      throw unwrapError(error, 'OpenCode workspace creation error');
    }
  }

  /**
   * Destroy a workspace — abort the underlying session.
   */
  async destroyWorkspace(workspaceId: string): Promise<void> {
    return this.cancelSession(workspaceId);
  }

  /**
   * Checkpoint: capture workspace state (file changes) + session state via API.
   * Uses the session shell to query git status in the repo.
   */
  async createCheckpoint(sessionId: string, repoPath = '/app'): Promise<OpenCodeCheckpoint> {
    try {
      const shellResult = await this.runShellCommand(
        sessionId,
        'git status --porcelain || true'
      );
      const fileChanges = parseGitPorcelain(shellResult.output || '');
      const snapshotId = `snap-${Date.now()}`;
      return {
        id: `cp-${Date.now()}`,
        sessionId,
        snapshotId,
        workspaceState: {
          worktreePath: repoPath,
          baseCommit: 'HEAD',
          isDirty: fileChanges.length > 0,
          fileChanges,
        },
        sessionState: { sessionId },
        timestamp: new Date().toISOString(),
      };
    } catch (error) {
      throw unwrapError(error, 'OpenCode create checkpoint error');
    }
  }

  /**
   * Resume a session (open reuses directory state; returns the session).
   */
  async resumeFromCheckpoint(sessionId: string): Promise<OpenCodeSession> {
    return this.getSession(sessionId);
  }

  /**
   * Get session details (GET /session/:id — returns array; take first).
   */
  async getSession(sessionId: string): Promise<OpenCodeSession> {
    try {
      const response = await this.client.get<OpenCodeSession[] | OpenCodeSession>(`/session/${sessionId}`);
      const data = response.data;
      return Array.isArray(data) ? (data[0] ?? { id: sessionId }) : (data ?? { id: sessionId });
    } catch (error) {
      throw unwrapError(error, 'OpenCode get session error');
    }
  }

  /**
   * Get workspace details — same as getSession (directory-scoped sessions).
   */
  async getWorkspace(workspaceId: string): Promise<OpenCodeWorkspace> {
    const session = await this.getSession(workspaceId);
    return {
      id: session.id,
      status: 'ready',
      worktreePath: (session.directory as string) ?? '/app',
      createdAt: new Date().toISOString(),
    };
  }
}

/**
 * Parse `git status --porcelain` output into file changes.
 */
export function parseGitPorcelain(output: string): OpenCodeFileChange[] {
  const changes: OpenCodeFileChange[] = [];
  const lines = output.split('\n').filter((l) => l.trim());
  for (const line of lines) {
    const staged = line.charAt(0);
    const unstaged = line.charAt(1);
    const path = line.substring(3).trim();
    if (!path) continue;
    let statusType: 'added' | 'modified' | 'deleted' = 'modified';
    if (staged === 'A' || staged === '?' || unstaged === '?' || unstaged === 'A') {
      statusType = 'added';
    } else if (staged === 'D' || unstaged === 'D') {
      statusType = 'deleted';
    }
    changes.push({ path, status: statusType });
  }
  return changes;
}
