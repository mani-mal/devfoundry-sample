import axios from 'axios';

const API_BASE_URL = '/api';

export type TaskStatus = 'Pending' | 'InProgress' | 'Completed' | 'Failed' | 'Cancelled';
export type TaskPhase = 'Submitted' | 'Qualified' | 'Running' | 'Validating' | 'AwaitingReview' | 'Completed' | 'Failed' | 'Cancelled' | 'Paused';
export type TaskOutcome = 'success' | 'failure' | 'partial';
export type TaskCheckpoint = 'started' | 'code_generated' | 'tests_passed' | 'deployed';
export type EvidenceItem = { type: string; content: string; provenance?: Record<string, unknown> };

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const healthApi = axios.create({
  baseURL: API_BASE_URL,
});

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('authToken');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const isLoginRequest = error.config?.url?.includes('/auth/login');
    if (error.response?.status === 401 && !isLoginRequest) {
      localStorage.removeItem('authToken');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export const apiClient = {
  getTasks: async (params?: {
    tenantId?: string;
    projectId?: string;
    status?: TaskStatus;
    phase?: TaskPhase;
    limit?: number;
    offset?: number;
  }) => {
    const response = await api.get('/tasks', { params });
    return response.data;
  },

  getTask: async (taskId: string) => {
    const response = await api.get(`/tasks/${taskId}`);
    return response.data;
  },

  createTask: async (task: {
    description: string;
    projectId: string;
    userId: string;
    baseCommit?: string;
    targetBranch?: string;
    skills?: string[];
    contextIds?: string[];
  }) => {
    const response = await api.post('/tasks', task);
    return response.data;
  },

  updateTask: async (taskId: string, updates: {
    status?: TaskStatus;
    phase?: TaskPhase;
    outcome?: TaskOutcome;
    checkpoint?: TaskCheckpoint;
    cancelledAt?: string;
  }) => {
    const response = await api.patch(`/tasks/${taskId}`, updates);
    return response.data;
  },

  deleteTask: async (taskId: string) => {
    await api.delete(`/tasks/${taskId}`);
  },

  getTaskOutcomes: async (taskId: string) => {
    const response = await api.get(`/tasks/${taskId}/outcomes`);
    return response.data;
  },

  getTaskEvidence: async (taskId: string) => {
    const response = await api.get(`/tasks/${taskId}/evidence`);
    return response.data;
  },

  addTaskEvidence: async (taskId: string, evidence: {
    type: EvidenceItem['type'];
    content: string;
    provenance?: Record<string, unknown>;
  }) => {
    const response = await api.post(`/tasks/${taskId}/evidence`, evidence);
    return response.data;
  },

  getHealth: async () => {
    const response = await healthApi.get('/health');
    return response.data;
  },

  getTools: async (params?: { enabled?: boolean; kind?: string }) => {
    const response = await api.get('/tools', { params });
    return response.data as { tools: Array<{ id: string; name: string; kind: string; description?: string; endpoint?: string; scopes: string[]; enabled: boolean; transport?: string }> };
  },

  searchTools: async (q: string) => {
    const response = await api.get('/tools/search', { params: { q } });
    return response.data as { tools: Array<{ id: string; name: string; description?: string; scopes: string[]; enabled: boolean }> };
  },

  setToolEnabled: async (id: string, enabled: boolean) => {
    const response = await api.post(`/tools/${id}/${enabled ? 'enable' : 'disable'}`);
    return response.data;
  },

  createTool: async (tool: {
    name: string;
    kind?: string;
    description?: string;
    endpoint?: string;
    transport?: string;
    scopes?: string[];
    enabled?: boolean;
  }) => {
    const response = await api.post('/tools', tool);
    return response.data;
  },

  updateTool: async (id: string, updates: {
    name?: string;
    kind?: string;
    description?: string;
    endpoint?: string;
    transport?: string;
    scopes?: string[];
  }) => {
    const response = await api.patch(`/tools/${id}`, updates);
    return response.data;
  },

  deleteTool: async (id: string) => {
    const response = await api.delete(`/tools/${id}`);
    return response.data;
  },

  installSkill: async (skill: {
    name: string;
    path: string;
    gitRepository: string;
    version?: string;
    description?: string;
  }) => {
    const response = await api.post('/skills', skill);
    return response.data;
  },

  getSkills: async (params?: { status?: string }) => {
    const response = await api.get('/skills', { params });
    return response.data as { skills: Array<{ id: string; name: string; version: string; digest: string; description?: string; approvalStatus: string }> };
  },

  setSkillStatus: async (id: string, status: string) => {
    const response = await api.patch(`/skills/${id}/status`, { status });
    return response.data;
  },

  getContextStats: async () => {
    const response = await api.get('/context/stats');
    return response.data as { nodes: number; edges: number; chunks: number };
  },

  getContextNodes: async (params?: { kind?: string; limit?: number }) => {
    const response = await api.get('/context/nodes', { params });
    return response.data as { nodes: Array<{ id: string; kind: string; sourceId: string; metadata: Record<string, unknown> }> };
  },

  searchContext: async (q: string) => {
    const response = await api.get('/context/search', { params: { q } });
    return response.data as { results: Array<{ id: string; location: string; text: string }> };
  },

  getMemory: async (params?: { scope?: string; promoted?: boolean }) => {
    const response = await api.get('/memory', { params });
    return response.data as { records: Array<{ id: string; scope: string; type: string; content: string; promoted: boolean }> };
  },

  getApplianceHealth: async () => {
    const response = await healthApi.get('/health');
    return response.data;
  },

  getGatewayModels: async () => {
    const response = await api.get('/gateway/models');
    return response.data as { models: any[] };
  },

  onboardGatewayModel: async (m: Record<string, unknown>) => {
    const response = await api.post('/gateway/models', m);
    return response.data;
  },

  editGatewayModel: async (slug: string, m: Record<string, unknown>) => {
    const response = await api.put(`/gateway/models/${slug}`, m);
    return response.data;
  },

  deleteGatewayModel: async (slug: string) => {
    const response = await api.delete(`/gateway/models/${slug}`);
    return response.data;
  },

  getGatewayApplications: async () => {
    const response = await api.get('/gateway/applications');
    return response.data as { applications: any[] };
  },

  createGatewayApplication: async (a: Record<string, unknown>) => {
    const response = await api.post('/gateway/applications', a);
    return response.data;
  },

  createGatewayApplicationToken: async (id: string, name?: string) => {
    const response = await api.post(`/gateway/applications/${id}/tokens`, { name });
    return response.data;
  },

  revokeGatewayToken: async (tokenId: string) => {
    const response = await api.post(`/gateway/tokens/${tokenId}/revoke`);
    return response.data;
  },

  setGatewayPolicy: async (id: string, p: Record<string, unknown>) => {
    const response = await api.put(`/gateway/applications/${id}/policy`, p);
    return response.data;
  },

  getReviewPacket: async (taskId: string) => {
    try {
      const response = await api.get(`/tasks/${taskId}/review-packet`);
      return response.data;
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 404) {
        return null;
      }
      throw error;
    }
  },

  getAdmission: async () => {
    const response = await api.get('/admission');
    return response.data as {
      limits: { cpu: number; ram: number; disk: number };
      queue: { depth: number; awaitingReview: number };
      resources: { cpu: { usage: number }; memory: { usage: number } };
    };
  },

  getAnalyticsOutcomes: async (params?: { days?: number; projectId?: string }) => {
    const response = await api.get('/analytics/outcomes', { params });
    return response.data as {
      total_tasks: number;
      completed_count: number;
      failed_count: number;
      cancelled_count: number;
      pending_count: number;
      avg_retries: number;
      avg_duration_s: number;
    };
  },

  getAnalyticsPhases: async () => {
    const response = await api.get('/analytics/phases');
    return response.data as { phases: Array<{ phase: string; count: number }> };
  },

  getAttempts: async (taskId: string) => {
    const response = await api.get(`/tasks/${taskId}/attempts`);
    return response.data as { attempts: Array<{ attempt_id: string; success: boolean; reason?: string; created_at: string }> };
  },

  cancelTask: async (taskId: string) => {
    const response = await api.post(`/tasks/${taskId}/cancel`);
    return response.data;
  },

  approveTask: async (taskId: string, disposition: 'approve' | 'reject', reason?: string) => {
    const response = await api.post(`/tasks/${taskId}/approve`, { disposition, reason });
    return response.data;
  },

  retryTask: async (taskId: string) => {
    const response = await api.post(`/tasks/${taskId}/retry`);
    return response.data;
  },

  pauseTask: async (taskId: string) => {
    const response = await api.post(`/tasks/${taskId}/pause`);
    return response.data;
  },

  resumeTask: async (taskId: string) => {
    const response = await api.post(`/tasks/${taskId}/resume`);
    return response.data;
  },

  getWorkspace: async (workspaceId: string) => {
    const response = await api.get(`/workspaces/${workspaceId}`);
    return response.data;
  },

  login: async (email: string, password: string) => {
    const response = await healthApi.post('/auth/login', { email, password });
    if (response.data.token) {
      localStorage.setItem('authToken', response.data.token);
    }
    return response.data;
  },

  logout: () => {
    localStorage.removeItem('authToken');
  },
};
