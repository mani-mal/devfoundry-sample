import axios, { AxiosInstance } from 'axios';
import { v4 as uuidv4 } from 'uuid';

export interface OpenCodeConfig {
  baseUrl: string;
  apiKey?: string;
  timeout?: number;
}

export interface SessionRequest {
  task?: string;
  instructions?: string;
  tools?: string[];
  context?: Record<string, unknown>;
}

export interface SessionResponse {
  sessionId: string;
  status: 'created' | 'running' | 'completed' | 'failed';
  message?: string;
}

export interface Event {
  id: string;
  type: string;
  timestamp: number;
  payload: Record<string, unknown>;
}

export interface WorkspaceConfig {
  worktreePath: string;
  baseCommit: string;
  environment?: Record<string, string>;
  resourceLimits?: {
    cpu?: number;
    memory?: string;
  };
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

  async createSession(task: string, context?: Record<string, unknown>): Promise<SessionResponse> {
    try {
      const response = await this.client.post<SessionResponse>('/sessions', {
        task,
        context,
      });
      return response.data;
    } catch (error) {
      throw new Error(`OpenCode session creation error: ${(error as Error).message}`);
    }
  }

  async sendMessage(sessionId: string, message: string): Promise<Event[]> {
    try {
      const response = await this.client.post<Event[]>('/sessions/:sessionId/messages', {
        message,
      });
      return response.data;
    } catch (error) {
      throw new Error(`OpenCode message error: ${(error as Error).message}`);
    }
  }

  async streamEvents(sessionId: string, lastEventId?: string): Promise<Event[]> {
    try {
      const response = await this.client.get<Event[]>('/sessions/:sessionId/events', {
        params: lastEventId ? { since: lastEventId } : undefined,
      });
      return response.data;
    } catch (error) {
      throw new Error(`OpenCode event streaming error: ${(error as Error).message}`);
    }
  }

  async interruptSession(sessionId: string): Promise<void> {
    try {
      await this.client.post(`/sessions/:sessionId/interrupt`);
    } catch (error) {
      throw new Error(`OpenCode interrupt error: ${(error as Error).message}`);
    }
  }

  async createWorkspace(config: WorkspaceConfig): Promise<string> {
    try {
      const response = await this.client.post<{ workspaceId: string }>('/workspaces', config);
      return response.data.workspaceId;
    } catch (error) {
      throw new Error(`OpenCode workspace creation error: ${(error as Error).message}`);
    }
  }

  async destroyWorkspace(workspaceId: string): Promise<void> {
    try {
      await this.client.delete(`/workspaces/:workspaceId`);
    } catch (error) {
      throw new Error(`OpenCode workspace destruction error: ${(error as Error).message}`);
    }
  }

  async healthCheck(): Promise<boolean> {
    try {
      const response = await this.client.get('/health');
      return response.status === 200;
    } catch {
      return false;
    }
  }

  public createCheckpoint(sessionId: string, workspaceId: string): string {
    return uuidv4();
  }
}
