import { OpenCodeAdapter } from '../src/opencode';
import type { OpenCodeSession } from '../src/opencode';

const mockGet = jest.fn();
const mockPost = jest.fn();
const mockDelete = jest.fn();

jest.mock('axios', () => ({
  __esModule: true,
  default: {
    create: jest.fn(() => ({
      get: (...args: unknown[]) => mockGet(...(args as [])),
      post: (...args: unknown[]) => mockPost(...(args as [])),
      delete: (...args: unknown[]) => mockDelete(...(args as [])),
    })),
    isAxiosError: (e: unknown) => !!(e as { isAxiosError?: boolean })?.isAxiosError,
  },
}));

const makeSession = (overrides: Partial<OpenCodeSession> = {}): OpenCodeSession => ({
  id: 'session-1',
  status: 'created',
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
  ...overrides,
});

describe('OpenCodeAdapter', () => {
  let adapter: OpenCodeAdapter;

  beforeEach(() => {
    jest.clearAllMocks();
    adapter = new OpenCodeAdapter({ baseUrl: 'http://localhost:4096' });
  });

  describe('createSession', () => {
    it('should POST /sessions with task, tools and context', async () => {
      const expected = makeSession();
      mockPost.mockResolvedValue({ data: expected });

      const result = await adapter.createSession({
        task: 'Fix authentication bug',
        tools: ['skill-git'],
        context: { projectId: 'project-1' },
      });

      expect(result).toEqual(expected);
      expect(mockPost).toHaveBeenCalledWith('/sessions', {
        task: 'Fix authentication bug',
        tools: ['skill-git'],
        context: { projectId: 'project-1' },
      });
    });

    it('should throw a descriptive error on failure', async () => {
      mockPost.mockRejectedValue(new Error('ECONNREFUSED'));

      await expect(adapter.createSession({ task: 'x' })).rejects.toThrow(
        'OpenCode session creation error: ECONNREFUSED'
      );
    });
  });

  describe('sendInput', () => {
    it('should POST message to session messages endpoint', async () => {
      const events = [{ id: 'e-1', type: 'message', timestamp: 'now', payload: {} }];
      mockPost.mockResolvedValue({ data: events });

      const result = await adapter.sendInput('session-1', 'Apply changes');

      expect(result).toEqual(events);
      expect(mockPost).toHaveBeenCalledWith('/sessions/session-1/messages', {
        message: 'Apply changes',
      });
    });

    it('should throw a descriptive error on failure', async () => {
      mockPost.mockRejectedValue(new Error('bad'));

      await expect(adapter.sendInput('s-1', 'hi')).rejects.toThrow(
        'OpenCode send input error: bad'
      );
    });
  });

  describe('streamEvents', () => {
    it('should GET events without params when no lastEventId', async () => {
      const events = [{ id: 'e-1', type: 'message', timestamp: 'now', payload: {} }];
      mockGet.mockResolvedValue({ data: events });

      const result = await adapter.streamEvents('session-1');

      expect(result).toEqual(events);
      expect(mockGet).toHaveBeenCalledWith('/sessions/session-1/events', {
        params: undefined,
      });
    });

    it('should pass since=lastEventId when provided', async () => {
      mockGet.mockResolvedValue({ data: [] });

      await adapter.streamEvents('session-1', 'e-0');

      expect(mockGet).toHaveBeenCalledWith('/sessions/session-1/events', {
        params: { since: 'e-0' },
      });
    });

    it('should throw a descriptive error on failure', async () => {
      mockGet.mockRejectedValue(new Error('stream-fail'));

      await expect(adapter.streamEvents('s-1')).rejects.toThrow(
        'OpenCode stream events error: stream-fail'
      );
    });
  });

  describe('cancelSession', () => {
    it('should POST to session cancel endpoint', async () => {
      mockPost.mockResolvedValue({ data: undefined });

      await adapter.cancelSession('session-1');

      expect(mockPost).toHaveBeenCalledWith('/sessions/session-1/cancel');
    });

    it('should throw a descriptive error on failure', async () => {
      mockPost.mockRejectedValue(new Error('cancel-fail'));

      await expect(adapter.cancelSession('s-1')).rejects.toThrow(
        'OpenCode cancel session error: cancel-fail'
      );
    });
  });

  describe('createWorkspace', () => {
    it('should POST /workspaces with baseCommit, environment and resourceLimits', async () => {
      const expected = { id: 'ws-1', status: 'ready', createdAt: 'now' };
      mockPost.mockResolvedValue({ data: expected });

      const config = {
        baseCommit: 'abc123',
        environment: { NODE_ENV: 'test' },
        resourceLimits: { cpu: 2, memory: '4G' },
      };
      const result = await adapter.createWorkspace(config);

      expect(result).toEqual(expected);
      expect(mockPost).toHaveBeenCalledWith('/workspaces', config);
    });

    it('should throw a descriptive error on failure', async () => {
      mockPost.mockRejectedValue(new Error('ws-fail'));

      await expect(
        adapter.createWorkspace({ baseCommit: 'x' })
      ).rejects.toThrow('OpenCode workspace creation error: ws-fail');
    });
  });

  describe('destroyWorkspace', () => {
    it('should DELETE workspace endpoint', async () => {
      mockDelete.mockResolvedValue({ data: undefined });

      await adapter.destroyWorkspace('ws-1');

      expect(mockDelete).toHaveBeenCalledWith('/workspaces/ws-1');
    });

    it('should throw a descriptive error on failure', async () => {
      mockDelete.mockRejectedValue(new Error('destroy-fail'));

      await expect(adapter.destroyWorkspace('ws-1')).rejects.toThrow(
        'OpenCode destroy workspace error: destroy-fail'
      );
    });
  });

  describe('createCheckpoint', () => {
    it('should POST to session checkpoints endpoint', async () => {
      const expected = {
        id: 'cp-1',
        sessionId: 'session-1',
        snapshotId: 'snapshot-1',
        workspaceState: {
          worktreePath: '/tmp/wt',
          baseCommit: 'abc',
          isDirty: false,
          fileChanges: [],
        },
        sessionState: { sessionId: 'session-1' },
        timestamp: 'now',
      };
      mockPost.mockResolvedValue({ data: expected });

      const result = await adapter.createCheckpoint('session-1');

      expect(result).toEqual(expected);
      expect(mockPost).toHaveBeenCalledWith('/sessions/session-1/checkpoints');
    });

    it('should throw a descriptive error on failure', async () => {
      mockPost.mockRejectedValue(new Error('cp-fail'));

      await expect(adapter.createCheckpoint('s-1')).rejects.toThrow(
        'OpenCode create checkpoint error: cp-fail'
      );
    });
  });

  describe('resumeFromCheckpoint', () => {
    it('should POST to checkpoint resume endpoint', async () => {
      const expected = makeSession({ id: 'session-2', status: 'running' });
      mockPost.mockResolvedValue({ data: expected });

      const result = await adapter.resumeFromCheckpoint('cp-1');

      expect(result).toEqual(expected);
      expect(mockPost).toHaveBeenCalledWith('/checkpoints/cp-1/resume');
    });

    it('should throw a descriptive error on failure', async () => {
      mockPost.mockRejectedValue(new Error('resume-fail'));

      await expect(adapter.resumeFromCheckpoint('cp-1')).rejects.toThrow(
        'OpenCode resume from checkpoint error: resume-fail'
      );
    });
  });

  describe('getSession / getWorkspace', () => {
    it('should GET session details', async () => {
      const expected = makeSession();
      mockGet.mockResolvedValue({ data: expected });

      expect(await adapter.getSession('session-1')).toEqual(expected);
      expect(mockGet).toHaveBeenCalledWith('/sessions/session-1');
    });

    it('should GET workspace details', async () => {
      const expected = { id: 'ws-1', status: 'ready', createdAt: 'now' };
      mockGet.mockResolvedValue({ data: expected });

      expect(await adapter.getWorkspace('ws-1')).toEqual(expected);
      expect(mockGet).toHaveBeenCalledWith('/workspaces/ws-1');
    });
  });

  describe('healthCheck', () => {
    it('should return true on 200', async () => {
      mockGet.mockResolvedValue({ status: 200 });

      expect(await adapter.healthCheck()).toBe(true);
    });

    it('should return false when unreachable', async () => {
      mockGet.mockRejectedValue(new Error('ECONNREFUSED'));

      expect(await adapter.healthCheck()).toBe(false);
    });
  });

  describe('apiKey authorization', () => {
    it('should attach Bearer authorization when apiKey configured', () => {
      const { default: axios } = require('axios');
      jest.clearAllMocks();

      new OpenCodeAdapter({ baseUrl: 'http://localhost:4096', apiKey: 'secret-token' });

      expect(axios.create).toHaveBeenCalledWith(
        expect.objectContaining({
          headers: { Authorization: 'Bearer secret-token' },
        })
      );
    });
  });
});
