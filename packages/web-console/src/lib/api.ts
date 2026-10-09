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

  getApplianceHealth: async () => {
    const response = await healthApi.get('/health');
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
