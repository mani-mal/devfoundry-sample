/**
 * RouteForge Integration Client
 * 
 * This client integrates with the RouteForge model routing service,
 * which is a Python application providing model routing and Langfuse integration.
 * 
 * RouteForge provides: Model routing, serving-endpoint connections,
 * gateway authentication/configuration, and existing Langfuse collection.
 * 
 * DevFoundry communicates with RouteForge via REST API endpoints.
 */

import axios, { AxiosInstance } from 'axios';

export interface RouteForgeConfig {
  baseUrl: string;
  apiKey?: string;
  timeout?: number;
}

export interface RouteForgeMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
  tool_calls?: RouteForgeToolCall[];
}

export interface RouteForgeToolCall {
  id: string;
  type: 'function';
  function: {
    name: string;
    arguments: string;
  };
}

export interface RouteForgeRequest {
  model: string;
  messages: RouteForgeMessage[];
  tools?: Array<{
    type: 'function';
    function: {
      name: string;
      description?: string;
      parameters: Record<string, unknown>;
    };
  }>;
  stream?: boolean;
  metadata?: Record<string, string>;
}

export interface RouteForgeResponse {
  id: string;
  object: string;
  created: number;
  model: string;
  choices: Array<{
    index: number;
    message: {
      role: 'assistant';
      content?: string;
      tool_calls?: RouteForgeToolCall[];
    };
    finish_reason?: string;
  }>;
  usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
}

export interface RouteForgeModel {
  id: string;
  object: string;
  created: number;
  owned_by: string;
}

export class RouteForgeClient {
  private client: AxiosInstance;
  private config: RouteForgeConfig;

  constructor(config: RouteForgeConfig) {
    this.config = config;
    this.client = axios.create({
      baseURL: config.baseUrl,
      timeout: config.timeout || 30000,
      headers: config.apiKey ? { Authorization: `Bearer ${config.apiKey}` } : {},
    });
  }

  /**
   * Health check - verify RouteForge is running
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
   * Get model completions from RouteForge
   */
  async generate(request: RouteForgeRequest): Promise<RouteForgeResponse> {
    try {
      const response = await this.client.post<RouteForgeResponse>(
        '/v1/chat/completions',
        request
      );
      return response.data;
    } catch (error) {
      throw new Error(`RouteForge API error: ${(error as Error).message}`);
    }
  }

  /**
   * Stream completions from RouteForge
   */
  async stream(request: RouteForgeRequest): Promise<NodeJS.ReadableStream> {
    try {
      const response = await this.client.post(
        '/v1/chat/completions',
        { ...request, stream: true },
        { responseType: 'stream' }
      );
      return response.data;
    } catch (error) {
      throw new Error(`RouteForge streaming error: ${(error as Error).message}`);
    }
  }

  /**
   * List available models from RouteForge
   */
  async listModels(): Promise<RouteForgeModel[]> {
    try {
      const response = await this.client.get<{ data: RouteForgeModel[] }>('/v1/models');
      return response.data.data;
    } catch (error) {
      throw new Error(`RouteForge list models error: ${(error as Error).message}`);
    }
  }

  /**
   * Get a specific model by ID
   */
  async getModel(modelId: string): Promise<RouteForgeModel | null> {
    try {
      const response = await this.client.get<{ data: RouteForgeModel }>(`/v1/models/${modelId}`);
      return response.data.data;
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 404) {
        return null;
      }
      throw new Error(`RouteForge get model error: ${(error as Error).message}`);
    }
  }

  /**
   * Create a Langfuse trace for task correlation
   */
  createTrace(taskId: string, name?: string): { traceId: string; spanId: string } {
    return {
      traceId: taskId,
      spanId: `span-${Date.now()}`,
    };
  }

  /**
   * Log evaluation results to RouteForge/Langfuse
   */
  async logEvaluation(
    traceId: string,
    evaluation: {
      name: string;
      score: number;
      metadata?: Record<string, unknown>;
    }
  ): Promise<void> {
    try {
      await this.client.post('/evaluations', {
        trace_id: traceId,
        ...evaluation,
      });
    } catch (error) {
      throw new Error(`RouteForge log evaluation error: ${(error as Error).message}`);
    }
  }

  /**
   * Get gateway configuration
   */
  async getConfiguration(): Promise<Record<string, unknown>> {
    try {
      const response = await this.client.get('/config');
      return response.data;
    } catch (error) {
      throw new Error(`RouteForge get configuration error: ${(error as Error).message}`);
    }
  }

  /**
   * Get supported routes
   */
  async getRoutes(): Promise<Array<{ name: string; model: string; conditions: Record<string, unknown> }>> {
    try {
      const response = await this.client.get<{ routes: Array<{ name: string; model: string; conditions: Record<string, unknown> }> }>('/routes');
      return response.data.routes;
    } catch (error) {
      throw new Error(`RouteForge get routes error: ${(error as Error).message}`);
    }
  }
}
