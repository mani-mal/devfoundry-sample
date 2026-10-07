import axios, { AxiosInstance } from 'axios';

export interface ContextForgeConfig {
  baseUrl: string;
  apiKey?: string;
  timeout?: number;
}

export interface Tool {
  id: string;
  name: string;
  description: string;
  schema: Record<string, unknown>;
  scopes: string[];
  enabled: boolean;
}

export interface Scope {
  id: string;
  name: string;
  description: string;
  tools: string[];
}

export class ContextForgeClient {
  private client: AxiosInstance;
  private config: ContextForgeConfig;

  constructor(config: ContextForgeConfig) {
    this.config = config;
    this.client = axios.create({
      baseURL: config.baseUrl,
      timeout: config.timeout || 30000,
      headers: config.apiKey ? { Authorization: `Bearer ${config.apiKey}` } : {},
    });
  }

  async listTools(): Promise<Tool[]> {
    try {
      const response = await this.client.get<{ tools: Tool[] }>('/tools');
      return response.data.tools;
    } catch (error) {
      throw new Error(`ContextForge list tools error: ${(error as Error).message}`);
    }
  }

  async getTool(toolId: string): Promise<Tool | null> {
    try {
      const response = await this.client.get<{ tool: Tool }>(`/tools/${toolId}`);
      return response.data.tool;
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 404) {
        return null;
      }
      throw new Error(`ContextForge get tool error: ${(error as Error).message}`);
    }
  }

  async callTool(toolId: string, input: Record<string, unknown>): Promise<Record<string, unknown>> {
    try {
      const response = await this.client.post<{ result: Record<string, unknown> }>(
        `/tools/${toolId}/call`,
        input
      );
      return response.data.result;
    } catch (error) {
      throw new Error(`ContextForge call tool error: ${(error as Error).message}`);
    }
  }

  async listScopes(): Promise<Scope[]> {
    try {
      const response = await this.client.get<{ scopes: Scope[] }>('/scopes');
      return response.data.scopes;
    } catch (error) {
      throw new Error(`ContextForge list scopes error: ${(error as Error).message}`);
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
}
