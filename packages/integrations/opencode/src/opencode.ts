/**
 * OpenCode Adapter for DevFoundry
 * 
 * This adapter integrates with OpenCode (a Python-based agent framework).
 * OpenCode provides: Context-aware agent execution, tool calling,
 * workspace management, and session persistence.
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
  status: 'created' | 'running' | 'completed' | 'failed';
  task?: string;
  context?: Record<string, unknown>;
  tools?: string[];
  createdAt: string;
  updatedAt: string;
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

export interface OpenCodeCheckpoint {
  id: string;
  sessionId: string;
  snapshotId: string;
  workspaceState: {
    worktreePath: string;
    baseCommit: string;
    isDirty: boolean;
    fileChanges: Array<{
      path: string;
      status: 'added' | 'modified' | 'deleted';
    }>;
  };
  sessionState: {
    sessionId: string;
    lastEventId?: string;
  };
  timestamp: string;
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
    });
  }

  /**
   * Health check - verify OpenCode is running
   */
  async healthCheck(): Promise<boolean> {
    try {
      const response = await this.client.get('/health');
      return response.status === 200;
    } catch {
      return false;
    }
  }

  /**
   * Create a new agent session
   */
  async createSession(request: OpenCodeTaskRequest): Promise<OpenCodeSession> {
    try {
      const response = await this.client.post<OpenCodeSession>('/sessions', request);
      return response.data;
    } catch (error) {
      throw new Error(`OpenCode session creation error: ${(error as Error).message}`);
    }
  }

  /**
   * Send input to a running session
   */
  async sendInput(sessionId: string, input: string): Promise<OpenCodeEvent[]> {
    try {
      const response = await this.client.post<OpenCodeEvent[]>(`/sessions/${sessionId}/messages`, {
        message: input,
      });
      return response.data;
    } catch (error) {
      throw new Error(`OpenCode send input error: ${(error as Error).message}`);
    }
  }

  /**
   * Stream events from a session
   */
  async streamEvents(sessionId: string, lastEventId?: string): Promise<OpenCodeEvent[]> {
    try {
      const response = await this.client.get<OpenCodeEvent[]>(`/sessions/${sessionId}/events`, {
        params: lastEventId ? { since: lastEventId } : undefined,
      });
      return response.data;
    } catch (error) {
      throw new Error(`OpenCode stream events error: ${(error as Error).message}`);
    }
  }

  /**
   * Request session cancellation
   */
  async cancelSession(sessionId: string): Promise<void> {
    try {
      await this.client.post(`/sessions/${sessionId}/cancel`);
    } catch (error) {
      throw new Error(`OpenCode cancel session error: ${(error as Error).message}`);
    }
  }

  /**
   * Create a new workspace
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
      const response = await this.client.post<OpenCodeWorkspace>('/workspaces', config);
      return response.data;
    } catch (error) {
      throw new Error(`OpenCode workspace creation error: ${(error as Error).message}`);
    }
  }

  /**
   * Destroy a workspace
   */
  async destroyWorkspace(workspaceId: string): Promise<void> {
    try {
      await this.client.delete(`/workspaces/${workspaceId}`);
    } catch (error) {
      throw new Error(`OpenCode destroy workspace error: ${(error as Error).message}`);
    }
  }

  /**
   * Create a checkpoint of session state
   */
  async createCheckpoint(sessionId: string): Promise<OpenCodeCheckpoint> {
    try {
      const response = await this.client.post<OpenCodeCheckpoint>(`/sessions/${sessionId}/checkpoints`);
      return response.data;
    } catch (error) {
      throw new Error(`OpenCode create checkpoint error: ${(error as Error).message}`);
    }
  }

  /**
   * Resume from a checkpoint
   */
  async resumeFromCheckpoint(checkpointId: string): Promise<OpenCodeSession> {
    try {
      const response = await this.client.post<OpenCodeSession>(`/checkpoints/${checkpointId}/resume`);
      return response.data;
    } catch (error) {
      throw new Error(`OpenCode resume from checkpoint error: ${(error as Error).message}`);
    }
  }

  /**
   * Get session details
   */
  async getSession(sessionId: string): Promise<OpenCodeSession> {
    try {
      const response = await this.client.get<OpenCodeSession>(`/sessions/${sessionId}`);
      return response.data;
    } catch (error) {
      throw new Error(`OpenCode get session error: ${(error as Error).message}`);
    }
  }

  /**
   * Get workspace details
   */
  async getWorkspace(workspaceId: string): Promise<OpenCodeWorkspace> {
    try {
      const response = await this.client.get<OpenCodeWorkspace>(`/workspaces/${workspaceId}`);
      return response.data;
    } catch (error) {
      throw new Error(`OpenCode get workspace error: ${(error as Error).message}`);
    }
  }
}
