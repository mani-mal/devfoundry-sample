/**
 * ContextForge Integration Client
 * 
 * This client integrates with the ContextForge MCP Gateway service,
 * which is a Python FastAPI application running separately.
 * 
 * ContextForge provides: MCP tool federation, REST/gRPC virtualization,
 * centralized governance, discovery, and observability.
 * 
 * DevFoundry communicates with ContextForge via REST API endpoints.
 */

import axios, { AxiosInstance } from 'axios';

export interface ContextForgeConfig {
  baseUrl: string;
  apiKey?: string;
  timeout?: number;
}

export interface ContextForgeTool {
  id: string;
  name: string;
  type: 'tool' | 'prompt' | 'resource';
  description?: string;
  schema?: Record<string, unknown>;
  scopes: string[];
  enabled: boolean;
  endpoint?: string;
  transport?: string;
}

export interface ContextForgeServer {
  id: string;
  name: string;
  description?: string;
  associatedTools: string[];
  transport: string;
  endpoint: string;
}

export interface ContextForgeScope {
  id: string;
  name: string;
  description?: string;
  tools: string[];
}

export interface ContextForgeResponse<T = unknown> {
  data: T;
  status: number;
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

  /**
   * Health check - verify ContextForge is running
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
   * Get all registered tools from ContextForge
   */
  async listTools(): Promise<ContextForgeTool[]> {
    try {
      const response = await this.client.get<{ tools: ContextForgeTool[] }>('/tools');
      return response.data.tools;
    } catch (error) {
      throw new Error(`ContextForge list tools error: ${(error as Error).message}`);
    }
  }

  /**
   * Get a specific tool by ID
   */
  async getTool(toolId: string): Promise<ContextForgeTool | null> {
    try {
      const response = await this.client.get<{ tool: ContextForgeTool }>(`/tools/${toolId}`);
      return response.data.tool;
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 404) {
        return null;
      }
      throw new Error(`ContextForge get tool error: ${(error as Error).message}`);
    }
  }

  /**
   * Call a tool through ContextForge
   */
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

  /**
   * List all registered servers (virtual MCP servers)
   */
  async listServers(): Promise<ContextForgeServer[]> {
    try {
      const response = await this.client.get<{ servers: ContextForgeServer[] }>('/servers');
      return response.data.servers;
    } catch (error) {
      throw new Error(`ContextForge list servers error: ${(error as Error).message}`);
    }
  }

  /**
   * Get a specific server by ID
   */
  async getServer(serverId: string): Promise<ContextForgeServer | null> {
    try {
      const response = await this.client.get<{ server: ContextForgeServer }>(`/servers/${serverId}`);
      return response.data.server;
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 404) {
        return null;
      }
      throw new Error(`ContextForge get server error: ${(error as Error).message}`);
    }
  }

  /**
   * List all scopes
   */
  async listScopes(): Promise<ContextForgeScope[]> {
    try {
      const response = await this.client.get<{ scopes: ContextForgeScope[] }>('/scopes');
      return response.data.scopes;
    } catch (error) {
      throw new Error(`ContextForge list scopes error: ${(error as Error).message}`);
    }
  }

  /**
   * Get server version info
   */
  async getVersion(): Promise<{ version: string; commit?: string }> {
    try {
      const response = await this.client.get('/version');
      return response.data;
    } catch (error) {
      throw new Error(`ContextForge get version error: ${(error as Error).message}`);
    }
  }

  /**
   * Register a new tool with ContextForge
   */
  async registerTool(tool: {
    name: string;
    type: 'tool' | 'prompt' | 'resource';
    description?: string;
    schema?: Record<string, unknown>;
    endpoint: string;
    transport: string;
  }): Promise<ContextForgeTool> {
    try {
      const response = await this.client.post<{ tool: ContextForgeTool }>('/tools', tool);
      return response.data.tool;
    } catch (error) {
      throw new Error(`ContextForge register tool error: ${(error as Error).message}`);
    }
  }

  /**
   * Create a virtual server bundling tools
   */
  async createServer(server: {
    name: string;
    description?: string;
    associatedTools: string[];
  }): Promise<ContextForgeServer> {
    try {
      const response = await this.client.post<{ server: ContextForgeServer }>('/servers', { server });
      return response.data.server;
    } catch (error) {
      throw new Error(`ContextForge create server error: ${(error as Error).message}`);
    }
  }
}
