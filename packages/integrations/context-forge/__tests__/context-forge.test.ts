import { ContextForgeClient } from '../src/context-forge';
import type { ContextForgeTool, ContextForgeServer, ContextForgeScope } from '../src/context-forge';

const mockGet = jest.fn();
const mockPost = jest.fn();

jest.mock('axios', () => ({
  __esModule: true,
  default: {
    create: jest.fn(() => ({
      get: (...args: unknown[]) => mockGet(...(args as [])),
      post: (...args: unknown[]) => mockPost(...(args as [])),
    })),
    isAxiosError: (e: unknown) => !!(e as { isAxiosError?: boolean })?.isAxiosError,
  },
}));

const makeTool = (overrides: Partial<ContextForgeTool> = {}): ContextForgeTool => ({
  id: 'tool-1',
  name: 'git_commit',
  type: 'tool',
  description: 'Commit changes',
  scopes: ['devfoundry:git'],
  enabled: false,
  ...overrides,
});

describe('ContextForgeClient', () => {
  let client: ContextForgeClient;

  beforeEach(() => {
    jest.clearAllMocks();
    client = new ContextForgeClient({ baseUrl: 'http://localhost:8001' });
  });

  describe('listTools', () => {
    it('should GET /tools and return the tools array', async () => {
      const tools = [makeTool(), makeTool({ id: 'tool-2', name: 'git_pr' })];
      mockGet.mockResolvedValue({ data: { tools } });

      const result = await client.listTools();

      expect(result).toEqual(tools);
      expect(mockGet).toHaveBeenCalledWith('/tools');
    });

    it('should throw a descriptive error on failure', async () => {
      mockGet.mockRejectedValue(new Error('boom'));

      await expect(client.listTools()).rejects.toThrow(
        'ContextForge list tools error: boom'
      );
    });
  });

  describe('getTool', () => {
    it('should return the tool when found', async () => {
      const tool = makeTool();
      mockGet.mockResolvedValue({ data: { tool } });

      const result = await client.getTool('tool-1');

      expect(result).toEqual(tool);
      expect(mockGet).toHaveBeenCalledWith('/tools/tool-1');
    });

    it('should return null on 404', async () => {
      const error = Object.assign(new Error('404'), {
        isAxiosError: true,
        response: { status: 404 },
      });
      mockGet.mockRejectedValue(error);

      const result = await client.getTool('missing');

      expect(result).toBeNull();
    });
  });

  describe('callTool', () => {
    it('should POST input to the tool call endpoint and return result', async () => {
      const result = { status: 'ok', output: 'committed' };
      mockPost.mockResolvedValue({ data: { result } });

      const input = { message: 'test commit' };
      const output = await client.callTool('tool-1', input);

      expect(output).toEqual(result);
      expect(mockPost).toHaveBeenCalledWith('/tools/tool-1/call', input);
    });

    it('should throw a descriptive error on failure', async () => {
      mockPost.mockRejectedValue(new Error('call-fail'));

      await expect(client.callTool('tool-1', {})).rejects.toThrow(
        'ContextForge call tool error: call-fail'
      );
    });
  });

  describe('listServers', () => {
    it('should GET /servers and return the servers array', async () => {
      const servers: ContextForgeServer[] = [
        {
          id: 'srv-1',
          name: 'git-server',
          associatedTools: ['tool-1'],
          transport: 'http',
          endpoint: 'http://git:8080',
        },
      ];
      mockGet.mockResolvedValue({ data: { servers } });

      const result = await client.listServers();

      expect(result).toEqual(servers);
      expect(mockGet).toHaveBeenCalledWith('/servers');
    });

    it('should throw a descriptive error on failure', async () => {
      mockGet.mockRejectedValue(new Error('servers-fail'));

      await expect(client.listServers()).rejects.toThrow(
        'ContextForge list servers error: servers-fail'
      );
    });
  });

  describe('getServer', () => {
    it('should return the server when found', async () => {
      const server: ContextForgeServer = {
        id: 'srv-1',
        name: 'git-server',
        associatedTools: [],
        transport: 'http',
        endpoint: 'http://git:8080',
      };
      mockGet.mockResolvedValue({ data: { server } });

      const result = await client.getServer('srv-1');

      expect(result).toEqual(server);
    });

    it('should return null on 404', async () => {
      const error = Object.assign(new Error('404'), {
        isAxiosError: true,
        response: { status: 404 },
      });
      mockGet.mockRejectedValue(error);

      const result = await client.getServer('missing');

      expect(result).toBeNull();
    });
  });

  describe('listScopes', () => {
    it('should GET /scopes and return the scopes array', async () => {
      const scopes: ContextForgeScope[] = [
        { id: 'scope-1', name: 'git', tools: ['tool-1'] },
      ];
      mockGet.mockResolvedValue({ data: { scopes } });

      const result = await client.listScopes();

      expect(result).toEqual(scopes);
      expect(mockGet).toHaveBeenCalledWith('/scopes');
    });

    it('should throw a descriptive error on failure', async () => {
      mockGet.mockRejectedValue(new Error('scopes-fail'));

      await expect(client.listScopes()).rejects.toThrow(
        'ContextForge list scopes error: scopes-fail'
      );
    });
  });

  describe('getVersion', () => {
    it('should GET /version and return version info', async () => {
      mockGet.mockResolvedValue({ data: { version: '1.2.3', commit: 'abc' } });

      const result = await client.getVersion();

      expect(result).toEqual({ version: '1.2.3', commit: 'abc' });
      expect(mockGet).toHaveBeenCalledWith('/version');
    });

    it('should throw a descriptive error on failure', async () => {
      mockGet.mockRejectedValue(new Error('version-fail'));

      await expect(client.getVersion()).rejects.toThrow(
        'ContextForge get version error: version-fail'
      );
    });
  });

  describe('registerTool', () => {
    it('should POST the tool definition to /tools', async () => {
      const created = makeTool();
      mockPost.mockResolvedValue({ data: { tool: created } });

      const tool = {
        name: 'git_commit',
        type: 'tool' as const,
        description: 'Commit changes',
        endpoint: 'http://git:8080/commit',
        transport: 'http',
      };
      const result = await client.registerTool(tool);

      expect(result).toEqual(created);
      expect(mockPost).toHaveBeenCalledWith('/tools', tool);
    });

    it('should throw a descriptive error on failure', async () => {
      mockPost.mockRejectedValue(new Error('register-fail'));

      await expect(
        client.registerTool({
          name: 'x',
          type: 'tool',
          endpoint: 'http://x',
          transport: 'http',
        })
      ).rejects.toThrow('ContextForge register tool error: register-fail');
    });
  });

  describe('createServer', () => {
    it('should POST the server bundle to /servers', async () => {
      const created: ContextForgeServer = {
        id: 'srv-1',
        name: 'git-server',
        associatedTools: ['tool-1'],
        transport: 'http',
        endpoint: 'http://git:8080',
      };
      mockPost.mockResolvedValue({ data: { server: created } });

      const server = {
        name: 'git-server',
        description: 'Git tools',
        associatedTools: ['tool-1'],
      };
      const result = await client.createServer(server);

      expect(result).toEqual(created);
      expect(mockPost).toHaveBeenCalledWith('/servers', { server });
    });

    it('should throw a descriptive error on failure', async () => {
      mockPost.mockRejectedValue(new Error('create-fail'));

      await expect(
        client.createServer({ name: 'x', associatedTools: [] })
      ).rejects.toThrow('ContextForge create server error: create-fail');
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

  describe('apiKey authorization', () => {
    it('should attach Bearer authorization when apiKey configured', () => {
      const { default: axios } = require('axios');
      jest.clearAllMocks();

      new ContextForgeClient({ baseUrl: 'http://localhost:8001', apiKey: 'secret-token' });

      expect(axios.create).toHaveBeenCalledWith(
        expect.objectContaining({
          headers: { Authorization: 'Bearer secret-token' },
        })
      );
    });
  });
});
