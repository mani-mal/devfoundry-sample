import { OpenCodeAdapter, parseGitPorcelain } from '../src/opencode';
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
    it('should POST /session with title from task', async () => {
      const expected = makeSession();
      mockPost.mockResolvedValue({ data: expected });

      const result = await adapter.createSession({
        task: 'Fix authentication bug',
        tools: ['skill-git'],
        context: { projectId: 'project-1' },
      });

      expect(result).toEqual(expected);
      expect(mockPost).toHaveBeenCalledWith('/session', {
        title: 'Fix authentication bug',
      });
    });

    it('should throw a descriptive error on failure', async () => {
      mockPost.mockRejectedValue(new Error('connection refused'));
      await expect(adapter.createSession({ task: 'x' })).rejects.toThrow(
        'OpenCode session creation error'
      );
    });
  });

  describe('listSessions', () => {
    it('should GET /session and return the array', async () => {
      const expected = [makeSession(), makeSession({ id: 'session-2' })];
      mockGet.mockResolvedValue({ data: expected });

      const result = await adapter.listSessions();
      expect(result).toEqual(expected);
      expect(mockGet).toHaveBeenCalledWith('/session');
    });
  });

  describe('sendInput', () => {
    it('should POST text part to /session/:id/message', async () => {
      const reply = { info: { id: 'msg-1', role: 'assistant' }, parts: [{ type: 'text', text: 'ok' }] };
      mockPost.mockResolvedValue({ data: reply });

      const result = await adapter.sendInput('session-1', 'hello');
      expect(result.length).toBeGreaterThan(0);
      expect(mockPost).toHaveBeenCalledWith(
        '/session/session-1/message',
        { parts: [{ type: 'text', text: 'hello' }] },
        expect.objectContaining({ timeout: expect.any(Number) })
      );
    });

    it('should throw a descriptive error on failure', async () => {
      mockPost.mockRejectedValue(new Error('timeout'));
      await expect(adapter.sendInput('session-1', 'x')).rejects.toThrow(
        'OpenCode send input error'
      );
    });
  });

  describe('runShellCommand', () => {
    it('should POST agent+command to /session/:id/shell and extract tool output', async () => {
      const reply = {
        info: { id: 'msg-2' },
        parts: [{ type: 'tool', tool: 'bash', state: { status: 'completed', output: 'hello-from-shell' } }],
      };
      mockPost.mockResolvedValue({ data: reply });

      const result = await adapter.runShellCommand('session-1', 'echo hello-from-shell');
      expect(result).toEqual({ status: 'completed', output: 'hello-from-shell' });
      expect(mockPost).toHaveBeenCalledWith(
        '/session/session-1/shell',
        { agent: 'build', command: 'echo hello-from-shell' },
        expect.objectContaining({ timeout: expect.any(Number) })
      );
    });

    it('should return empty output when no tool part', async () => {
      mockPost.mockResolvedValue({ data: { info: {}, parts: [] } });
      const result = await adapter.runShellCommand('session-1', 'ls');
      expect(result).toEqual({ status: 'unknown', output: '' });
    });

    it('should throw a descriptive error on failure', async () => {
      mockPost.mockRejectedValue(new Error('boom'));
      await expect(adapter.runShellCommand('session-1', 'ls')).rejects.toThrow(
        'OpenCode shell command error'
      );
    });
  });

  describe('cancelSession', () => {
    it('should POST to /session/:id/abort', async () => {
      mockPost.mockResolvedValue({ data: {} });
      await adapter.cancelSession('session-1');
      expect(mockPost).toHaveBeenCalledWith('/session/session-1/abort');
    });

    it('should throw a descriptive error on failure', async () => {
      mockPost.mockRejectedValue(new Error('gone'));
      await expect(adapter.cancelSession('session-1')).rejects.toThrow(
        'OpenCode cancel session error'
      );
    });
  });

  describe('createWorkspace', () => {
    it('should create a session and map it to a ready workspace', async () => {
      const session = makeSession({ id: 'ws-1', directory: '/app' });
      mockPost.mockResolvedValue({ data: session });

      const result = await adapter.createWorkspace({ baseCommit: 'abc123' });
      expect(result).toEqual({
        id: 'ws-1',
        status: 'ready',
        worktreePath: '/app',
        baseCommit: 'abc123',
        environment: undefined,
        createdAt: expect.any(String),
      });
    });

    it('should throw a descriptive error when session creation fails', async () => {
      mockPost.mockRejectedValue(new Error('nope'));
      await expect(adapter.createWorkspace({ baseCommit: 'abc' })).rejects.toThrow(
        'OpenCode workspace creation error'
      );
    });
  });

  describe('destroyWorkspace', () => {
    it('should abort the underlying session', async () => {
      mockPost.mockResolvedValue({ data: {} });
      await adapter.destroyWorkspace('ws-1');
      expect(mockPost).toHaveBeenCalledWith('/session/ws-1/abort');
    });
  });

  describe('createCheckpoint', () => {
    it('should capture workspace state from git via shell and build a checkpoint', async () => {
      mockPost.mockResolvedValue({
        data: {
          info: {},
          parts: [{ type: 'tool', state: { status: 'completed', output: ' M src/a.ts\n?? new.ts' } }],
        },
      });

      const result = await adapter.createCheckpoint('session-1', '/app');
      expect(result.sessionId).toBe('session-1');
      expect(result.snapshotId).toMatch(/^snap-/);
      expect(result.workspaceState.isDirty).toBe(true);
      expect(result.workspaceState.fileChanges).toEqual([
        { path: 'src/a.ts', status: 'modified' },
        { path: 'new.ts', status: 'added' },
      ]);
    });

    it('should throw a descriptive error when the shell call fails', async () => {
      mockPost.mockRejectedValue(new Error('fail'));
      await expect(adapter.createCheckpoint('session-1')).rejects.toThrow(
        'OpenCode create checkpoint error'
      );
    });
  });

  describe('getSession', () => {
    it('should unwrap array responses to the first session', async () => {
      const session = makeSession({ id: 'session-1' });
      mockGet.mockResolvedValue({ data: [session] });
      const result = await adapter.getSession('session-1');
      expect(result).toEqual(session);
    });

    it('should pass through object responses', async () => {
      const session = makeSession({ id: 'session-1' });
      mockGet.mockResolvedValue({ data: session });
      const result = await adapter.getSession('session-1');
      expect(result).toEqual(session);
    });
  });

  describe('healthCheck', () => {
    it('should GET / and return true on 200', async () => {
      mockGet.mockResolvedValue({ status: 200 });
      expect(await adapter.healthCheck()).toBe(true);
    });

    it('should return false on failure', async () => {
      mockGet.mockRejectedValue(new Error('down'));
      expect(await adapter.healthCheck()).toBe(false);
    });
  });
});

describe('parseGitPorcelain', () => {
  it('should parse added, modified and deleted files', () => {
    const output = 'A  added.ts\n M modified.ts\n D deleted.ts\n?? untracked.ts';
    expect(parseGitPorcelain(output)).toEqual([
      { path: 'added.ts', status: 'added' },
      { path: 'modified.ts', status: 'modified' },
      { path: 'deleted.ts', status: 'deleted' },
      { path: 'untracked.ts', status: 'added' },
    ]);
  });

  it('should return empty for empty output', () => {
    expect(parseGitPorcelain('')).toEqual([]);
  });

  it('should skip lines without a path', () => {
    expect(parseGitPorcelain(' M \n\n A ')).toEqual([]);
  });
});
