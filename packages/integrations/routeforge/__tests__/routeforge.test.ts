import { RouteForgeClient } from '../src/routeforge';
import type {
  RouteForgeRequest,
  RouteForgeResponse,
  RouteForgeModel,
} from '../src/routeforge';

const makeResponse = (overrides: Partial<RouteForgeResponse> = {}): RouteForgeResponse => ({
  id: 'chat-mock-1',
  object: 'chat.completion',
  created: Date.now(),
  model: 'llama-2-7b',
  choices: [
    {
      index: 0,
      message: { role: 'assistant', content: 'Mock response' },
      finish_reason: 'stop',
    },
  ],
  usage: { prompt_tokens: 10, completion_tokens: 10, total_tokens: 20 },
  ...overrides,
});

const makeRequest = (overrides: Partial<RouteForgeRequest> = {}): RouteForgeRequest => ({
  model: 'llama-2-7b',
  messages: [
    { role: 'system', content: 'You are a helpful assistant' },
    { role: 'user', content: 'Generate a bug fix' },
  ],
  ...overrides,
});

const mockGenerate = jest.fn();
const mockStream = jest.fn();
const mockGet = jest.fn();
const mockPost = jest.fn();

jest.mock('axios', () => ({
  __esModule: true,
  default: {
    create: jest.fn(() => ({
      get: (...args: unknown[]) => mockGet(...(args as [])),
      post: (...args: unknown[]) => {
        const [url] = args as [string];
        if (url === '/evaluations') return mockPost(...(args as []));
        if (url === '/v1/chat/completions' && (args[1] as { stream?: boolean })?.stream) {
          return mockStream(...(args as []));
        }
        return mockGenerate(...(args as []));
      },
      isAxiosError: false,
    })),
    isAxiosError: (e: unknown) => !!(e as { isAxiosError?: boolean })?.isAxiosError,
  },
}));

describe('RouteForgeClient', () => {
  let client: RouteForgeClient;

  beforeEach(() => {
    jest.clearAllMocks();
    client = new RouteForgeClient({ baseUrl: 'http://localhost:8000' });
  });

  describe('generate', () => {
    it('should POST to /v1/chat/completions and return the response', async () => {
      const expected = makeResponse();
      mockGenerate.mockResolvedValue({ data: expected });

      const result = await client.generate(makeRequest());

      expect(result).toEqual(expected);
      expect(mockGenerate).toHaveBeenCalledWith(
        '/v1/chat/completions',
        makeRequest()
      );
    });

    it('should include tools and metadata in the request body', async () => {
      mockGenerate.mockResolvedValue({ data: makeResponse() });

      const request = makeRequest({
        tools: [
          {
            type: 'function',
            function: {
              name: 'git_apply_patch',
              description: 'Apply a patch',
              parameters: { type: 'object', properties: {} },
            },
          },
        ],
        metadata: { tenant_id: 't-1', task_id: 'task-1' },
      });
      await client.generate(request);

      const body = mockGenerate.mock.calls[0][1] as RouteForgeRequest;
      expect(body.tools?.[0].function.name).toBe('git_apply_patch');
      expect(body.metadata?.task_id).toBe('task-1');
    });

    it('should throw a descriptive error when the API fails', async () => {
      mockGenerate.mockRejectedValue(new Error('connect ECONNREFUSED'));

      await expect(client.generate(makeRequest())).rejects.toThrow(
        'RouteForge API error: connect ECONNREFUSED'
      );
    });
  });

  describe('stream', () => {
    it('should set stream: true and return a readable stream', async () => {
      const fakeStream = { pipe: jest.fn() };
      mockStream.mockResolvedValue({ data: fakeStream });

      const stream = await client.stream(makeRequest());

      expect(stream).toBe(fakeStream);
      const body = mockStream.mock.calls[0][1] as RouteForgeRequest;
      expect(body.stream).toBe(true);
    });

    it('should throw a descriptive streaming error on failure', async () => {
      mockStream.mockRejectedValue(new Error('timeout'));

      await expect(client.stream(makeRequest())).rejects.toThrow(
        'RouteForge streaming error: timeout'
      );
    });
  });

  describe('listModels', () => {
    it('should GET /v1/models and return the data array', async () => {
      const models: RouteForgeModel[] = [
        { id: 'llama-2-7b', object: 'model', created: 1, owned_by: 'meta' },
        { id: 'gpt-4', object: 'model', created: 2, owned_by: 'openai' },
      ];
      mockGet.mockResolvedValue({ data: { data: models } });

      const result = await client.listModels();

      expect(result).toEqual(models);
      expect(mockGet).toHaveBeenCalledWith('/v1/models');
    });

    it('should throw a descriptive error on failure', async () => {
      mockGet.mockRejectedValue(new Error('boom'));

      await expect(client.listModels()).rejects.toThrow(
        'RouteForge list models error: boom'
      );
    });
  });

  describe('getModel', () => {
    it('should return the model when found', async () => {
      const model: RouteForgeModel = {
        id: 'gpt-4',
        object: 'model',
        created: 2,
        owned_by: 'openai',
      };
      mockGet.mockResolvedValue({ data: { data: model } });

      const result = await client.getModel('gpt-4');

      expect(result).toEqual(model);
    });

    it('should return null on 404', async () => {
      const error = Object.assign(new Error('404'), {
        isAxiosError: true,
        response: { status: 404 },
      });
      mockGet.mockRejectedValue(error);

      const result = await client.getModel('missing');

      expect(result).toBeNull();
    });
  });

  describe('createTrace', () => {
    it('should return a stable traceId and spanId', () => {
      const trace = client.createTrace('task-1', 'task-execution');

      expect(trace.traceId).toBe('task-1');
      expect(trace.spanId).toBeDefined();
      expect(trace.spanId).toMatch(/^span-/);
    });
  });

  describe('logEvaluation', () => {
    it('should POST evaluation results to /evaluations', async () => {
      mockPost.mockResolvedValue({ data: {} });

      await client.logEvaluation('trace-1', {
        name: 'test-coverage',
        score: 0.9,
        metadata: { projectId: 'p-1' },
      });

      expect(mockPost).toHaveBeenCalledWith('/evaluations', {
        trace_id: 'trace-1',
        name: 'test-coverage',
        score: 0.9,
        metadata: { projectId: 'p-1' },
      });
    });

    it('should throw a descriptive error on failure', async () => {
      mockPost.mockRejectedValue(new Error('nope'));

      await expect(
        client.logEvaluation('trace-1', { name: 'x', score: 1 })
      ).rejects.toThrow('RouteForge log evaluation error: nope');
    });
  });

  describe('getConfiguration and getRoutes', () => {
    it('should GET /config and return data', async () => {
      const config = { routes: [{ name: 'default' }] };
      mockGet.mockResolvedValue({ data: config });

      const result = await client.getConfiguration();

      expect(result).toEqual(config);
      expect(mockGet).toHaveBeenCalledWith('/config');
    });

    it('should GET /routes and return the routes array', async () => {
      const routes = [{ name: 'default', model: 'gpt-4', conditions: {} }];
      mockGet.mockResolvedValue({ data: { routes } });

      const result = await client.getRoutes();

      expect(result).toEqual(routes);
      expect(mockGet).toHaveBeenCalledWith('/routes');
    });
  });

  describe('healthCheck', () => {
    it('should return true on 200', async () => {
      mockGet.mockResolvedValue({ status: 200 });

      expect(await client.healthCheck()).toBe(true);
    });

    it('should return false when unreachable', async () => {
      mockGet.mockRejectedValue(new Error('ECONNREFUSED'));

      expect(await client.healthCheck()).toBe(false);
    });
  });
});
