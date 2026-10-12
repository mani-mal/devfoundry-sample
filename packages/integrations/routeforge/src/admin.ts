/**
 * RouteForge Admin Client
 *
 * This client integrates with the RouteForge model gateway admin APIs,
 * which manage onboarded models, applications, tokens, and routing policies.
 *
 * All admin endpoints authenticate via the `rf_admin_session` cookie
 * (NOT a Bearer token), established through POST /admin/login.
 */

import { AxiosInstance } from 'axios';
import axios from 'axios';

export interface RouteForgeOnboardModel {
  slug: string;
  display_name: string;
  tier: string;
  endpoint: string;
  price_input: number;
  price_output: number;
  api_key_env?: string | null;
  price_cached_input?: number | null;
  quality?: number | null;
  context_window?: number | null;
  allowed_app_ids?: string[] | null;
  notes?: string | null;
  enabled?: boolean;
  region?: string | null;
  prompt_retention?: string | null;
  accepts_raw_sensitive?: boolean | null;
}

export interface RouteForgeApplication {
  id: string;
  name: string;
  owner_email?: string | null;
  status?: string;
  default_residency?: string;
}

export interface RouteForgeApplicationInput {
  id: string;
  name: string;
  owner_email?: string | null;
  default_residency?: string;
}

export interface RouteForgeApplicationUpdate {
  name?: string;
  owner_email?: string | null;
  status?: string;
  default_residency?: string;
}

export interface RouteForgePolicy {
  allowed_tiers?: string[] | null;
  allowed_providers?: string[] | null;
  allowed_models?: string[] | null;
  residency?: string | null;
  max_spend_usd_per_day?: number | null;
  max_cost_usd_per_request?: number | null;
}

export interface RouteForgeAdminSession {
  email: string;
}

export interface RouteForgeAdminConfig {
  baseUrl: string;
  email: string;
  password: string;
  timeout?: number;
}

export class RouteForgeAdminClient {
  private client: AxiosInstance;
  private config: RouteForgeAdminConfig;
  private adminSession: string | null = null;

  constructor(config: RouteForgeAdminConfig) {
    this.config = config;
    this.client = axios.create({
      baseURL: config.baseUrl,
      timeout: config.timeout || 30000,
      withCredentials: false,
    });
  }

  private wrapError(label: string, error: unknown): never {
    throw new Error(`RouteForge ${label} error: ${(error as Error).message}`);
  }

  /**
   * Login as admin - stores the rf_admin_session cookie for subsequent calls
   */
  async login(): Promise<void> {
    try {
      const response = await this.client.post('/admin/login', {
        email: this.config.email,
        password: this.config.password,
      });
      const setCookie = response.headers?.['set-cookie'];
      if (Array.isArray(setCookie)) {
        for (const cookie of setCookie) {
          const [pair] = cookie.split(';');
          const [name, value] = pair.split('=');
          if (name?.trim() === 'rf_admin_session' && value) {
            this.adminSession = value.trim();
          }
        }
      }
      if (this.adminSession) {
        this.client.defaults.headers.common['Cookie'] = `rf_admin_session=${this.adminSession}`;
      }
    } catch (error) {
      this.wrapError('admin login', error);
    }
  }

  /**
   * Verify admin session - returns the authenticated admin's email
   */
  async me(): Promise<RouteForgeAdminSession> {
    try {
      const response = await this.client.get<RouteForgeAdminSession>('/admin/me');
      return response.data;
    } catch (error) {
      this.wrapError('admin me', error);
    }
  }

  /**
   * List onboarded models from RouteForge admin
   */
  async listModels(): Promise<unknown[]> {
    try {
      const response = await this.client.get<unknown[]>('/admin/infra/models');
      return response.data;
    } catch (error) {
      this.wrapError('admin list models', error);
    }
  }

  /**
   * Onboard a model to the RouteForge gateway
   */
  async onboardModel(model: RouteForgeOnboardModel): Promise<unknown> {
    try {
      const response = await this.client.post('/admin/infra/models', model);
      return response.data;
    } catch (error) {
      this.wrapError('admin onboard model', error);
    }
  }

  /**
   * Edit an onboarded model by slug
   */
  async editModel(slug: string, model: RouteForgeOnboardModel): Promise<unknown> {
    try {
      const response = await this.client.put(`/admin/infra/models/${slug}`, model);
      return response.data;
    } catch (error) {
      this.wrapError('admin edit model', error);
    }
  }

  /**
   * Delete an onboarded model by slug
   */
  async deleteModel(slug: string): Promise<unknown> {
    try {
      const response = await this.client.delete(`/admin/infra/models/${slug}`);
      return response.data;
    } catch (error) {
      this.wrapError('admin delete model', error);
    }
  }

  /**
   * List applications registered with the gateway
   */
  async listApplications(): Promise<unknown[]> {
    try {
      const response = await this.client.get<unknown[]>('/admin/applications');
      return response.data;
    } catch (error) {
      this.wrapError('admin list applications', error);
    }
  }

  /**
   * Create a new gateway application
   */
  async createApplication(app: RouteForgeApplicationInput): Promise<unknown> {
    try {
      const response = await this.client.post('/admin/applications', app);
      return response.data;
    } catch (error) {
      this.wrapError('admin create application', error);
    }
  }

  /**
   * Get a specific application by ID
   */
  async getApplication(appId: string): Promise<unknown | null> {
    try {
      const response = await this.client.get(`/admin/applications/${appId}`);
      return response.data;
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 404) {
        return null;
      }
      this.wrapError('admin get application', error);
    }
  }

  /**
   * Update a gateway application
   */
  async updateApplication(appId: string, update: RouteForgeApplicationUpdate): Promise<unknown> {
    try {
      const response = await this.client.patch(`/admin/applications/${appId}`, update);
      return response.data;
    } catch (error) {
      this.wrapError('admin update application', error);
    }
  }

  /**
   * Create a scoped application token
   */
  async createApplicationToken(appId: string, name?: string): Promise<unknown> {
    try {
      const response = await this.client.post(`/admin/applications/${appId}/tokens`, {
        name: name ?? 'default',
      });
      return response.data;
    } catch (error) {
      this.wrapError('admin create application token', error);
    }
  }

  /**
   * Revoke an application token by ID
   */
  async revokeToken(tokenId: string): Promise<unknown> {
    try {
      const response = await this.client.post(`/admin/tokens/${tokenId}/revoke`);
      return response.data;
    } catch (error) {
      this.wrapError('admin revoke token', error);
    }
  }

  /**
   * Set the routing policy for an application
   */
  async setPolicy(appId: string, policy: RouteForgePolicy): Promise<unknown> {
    try {
      const body = Object.fromEntries(
        Object.entries(policy).filter(([, value]) => value !== null && value !== undefined)
      );
      const response = await this.client.put(`/admin/applications/${appId}/policy`, body);
      return response.data;
    } catch (error) {
      this.wrapError('admin set policy', error);
    }
  }
}
