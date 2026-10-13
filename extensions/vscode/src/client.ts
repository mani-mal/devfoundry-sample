export interface DevFoundryTask {
  id: string;
  tenantId?: string;
  projectId?: string;
  userId?: string;
  status: string;
  phase: string;
  description: string;
  baseCommit?: string;
  targetBranch?: string;
  workspaceId?: string;
  modelRoute?: string;
  capacityProfile?: string;
  createdAt?: string;
  updatedAt?: string;
  startedAt?: string;
  completedAt?: string;
  retryCount?: number;
}

export interface ContextSearchResult {
  id: string;
  location: string;
  revision?: string;
  text: string;
  node?: { id?: string; kind?: string; sourceId?: string };
}

export class DevFoundryApiError extends Error {
  constructor(
    message: string,
    public readonly status: number
  ) {
    super(message);
    this.name = 'DevFoundryApiError';
  }
}

const TIMEOUT_MS = 5000;

export class DevFoundryClient {
  constructor(
    private readonly getBaseUrl: () => string,
    private readonly getToken: () => Promise<string | undefined>,
    private readonly setToken: (token: string | undefined) => Promise<void>
  ) {}

  async login(email: string, password: string): Promise<{ user: { email: string } }> {
    const body = await this.request<{ token?: string; user?: { email: string } }>(
      '/api/auth/login',
      {
        method: 'POST',
        body: JSON.stringify({ email, password }),
        skipAuth: true,
      }
    );
    if (!body.token) {
      throw new DevFoundryApiError('Login response contained no token', 500);
    }
    await this.setToken(body.token);
    return { user: body.user ?? { email } };
  }

  async logout(): Promise<void> {
    await this.setToken(undefined);
  }

  async isLoggedIn(): Promise<boolean> {
    return (await this.getToken()) !== undefined;
  }

  async getTasks(): Promise<DevFoundryTask[]> {
    const body = await this.request<{ tasks?: DevFoundryTask[] }>('/api/tasks?limit=50');
    return body.tasks ?? [];
  }

  async getTask(id: string): Promise<DevFoundryTask> {
    return this.request<DevFoundryTask>(`/api/tasks/${encodeURIComponent(id)}`);
  }

  async createTask(description: string, projectId: string, userId: string): Promise<DevFoundryTask> {
    return this.request<DevFoundryTask>('/api/tasks', {
      method: 'POST',
      body: JSON.stringify({ description, projectId, userId }),
    });
  }

  async cancelTask(id: string): Promise<DevFoundryTask> {
    return this.request<DevFoundryTask>(`/api/tasks/${encodeURIComponent(id)}/cancel`, {
      method: 'POST',
    });
  }

  async retryTask(id: string): Promise<DevFoundryTask> {
    return this.request<DevFoundryTask>(`/api/tasks/${encodeURIComponent(id)}/retry`, {
      method: 'POST',
    });
  }

  async getReviewPacket(
    id: string
  ): Promise<{ packet: Record<string, unknown>; generatedAt?: string }> {
    return this.request<{ packet: Record<string, unknown>; generatedAt?: string }>(
      `/api/tasks/${encodeURIComponent(id)}/review-packet`
    );
  }

  async getAttempts(
    id: string
  ): Promise<Array<{ attemptId?: string; success?: boolean; reason?: string; createdAt?: string }>> {
    const body = await this.request<{
      attempts?: Array<{ attemptId?: string; success?: boolean; reason?: string; createdAt?: string }>;
    }>(`/api/tasks/${encodeURIComponent(id)}/attempts`);
    return body.attempts ?? [];
  }

  /**
   * Search authorized context. Returns [] with a `notAvailable` flag when the
   * installation does not expose the route (404) — no behavior is invented
   * beyond this graceful fallback.
   */
  async searchContext(
    query: string
  ): Promise<{ results: ContextSearchResult[]; notAvailable?: boolean }> {
    try {
      const body = await this.request<{ results?: ContextSearchResult[] }>(
        `/api/context/search?q=${encodeURIComponent(query)}`
      );
      return { results: body.results ?? [] };
    } catch (err) {
      if (err instanceof DevFoundryApiError && err.status === 404) {
        return { results: [], notAvailable: true };
      }
      throw err;
    }
  }

  private async request<T>(
    path: string,
    init?: { method?: string; body?: string; skipAuth?: boolean }
  ): Promise<T> {
    const baseUrl = this.getBaseUrl().replace(/\/$/, '');
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (!init?.skipAuth) {
      const token = await this.getToken();
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
    let res: Response;
    try {
      res = await fetch(`${baseUrl}${path}`, {
        method: init?.method ?? 'GET',
        headers,
        body: init?.body,
        signal: controller.signal,
      });
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        throw new DevFoundryApiError(`DevFoundry API request timed out (${TIMEOUT_MS}ms)`, 504);
      }
      throw new DevFoundryApiError(
        `Cannot reach DevFoundry API at ${baseUrl}: ${err instanceof Error ? err.message : String(err)}`,
        503
      );
    } finally {
      clearTimeout(timer);
    }

    if (!res.ok) {
      let detail = '';
      try {
        const payload = (await res.json()) as { error?: string };
        detail = payload.error ? `: ${payload.error}` : '';
      } catch {
        detail = '';
      }
      throw new DevFoundryApiError(`DevFoundry API ${res.status}${detail}`, res.status);
    }

    return (await res.json()) as T;
  }
}
