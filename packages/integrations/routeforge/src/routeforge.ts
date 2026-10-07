import axios, { AxiosInstance } from 'axios';
import { v4 as uuidv4 } from 'uuid';

export interface RouteForgeConfig {
  baseUrl: string;
  apiKey?: string;
  timeout?: number;
}

export interface RouteForgeRequest {
  model: string;
  messages: Array<{
    role: 'system' | 'user' | 'assistant';
    content: string;
  }>;
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
      tool_calls?: Array<{
        id: string;
        type: 'function';
        function: {
          name: string;
          arguments: string;
        };
      }>;
    };
    finish_reason?: string;
  }>;
  usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
}

export interface LangfuseTrace {
  traceId: string;
  spanId?: string;
  name: string;
  type: 'llm' | 'span' | 'event';
  metadata?: Record<string, unknown>;
  startTime: number;
  endTime?: number;
  input?: Record<string, unknown>;
  output?: Record<string, unknown>;
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

  public createTrace(name: string): LangfuseTrace {
    return {
      traceId: uuidv4(),
      name,
      type: 'llm',
      startTime: Date.now(),
    };
  }

  public async logTrace(trace: LangfuseTrace): Promise<void> {
    // TODO: Send trace to Langfuse
  }

  public async healthCheck(): Promise<boolean> {
    try {
      const response = await this.client.get('/health');
      return response.status === 200;
    } catch {
      return false;
    }
  }
}
