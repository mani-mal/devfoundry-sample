import axios from 'axios';
import { RouteForgeAdminClient } from '../src/admin';
import type {
  RouteForgeOnboardModel,
  RouteForgePolicy,
} from '../src/admin';

const makeOnboardModel = (overrides: Partial<RouteForgeOnboardModel> = {}): RouteForgeOnboardModel => ({
  slug: 'llama-2-7b',
  display_name: 'Llama 2 7B',
  tier: 'small',
  endpoint: 'http://vllm:8000/v1',
  price_input: 0.1,
  price_output: 0.2,
  ...overrides,
});

const mockLoginPost = jest.fn();
const mockGet = jest.fn();
const mockPost = jest.fn();
const mockPut = jest.fn();
const mockPatch = jest.fn();
const mockDelete = jest.fn();

jest.mock('axios', () => ({
  __esModule: true,
  default: {
    create: jest.fn(() => ({
      defaults: { headers: { common: {} } },
      post: (...args: unknown[]) => {
        const [url] = args as [string];
        if (url === '/admin/login') return mockLoginPost(...(args as []));
        return mockPost(...(args as []));
      },
      get: (...args: unknown[]) => mockGet(...(args as [])),
      put: (...args: unknown[]) => mockPut(...(args as [])),
      patch: (...args: unknown[]) => mockPatch(...(args as [])),
      delete: (...args: unknown[]) => mockDelete(...(args as [])),
      isAxiosError: false,
    })),
    isAxiosError: (e: unknown) => !!(e as { isAxiosError?: boolean })?.isAxiosError,
  },
}));

describe('RouteForgeAdminClient', () => {
  let client: RouteForgeAdminClient;

  beforeEach(() => {
    jest.clearAllMocks();
    client = new RouteForgeAdminClient({
      baseUrl: 'http://localhost:8000',
      email: 'admin@example.com',
      password: 'secret',
    });
  });

  describe('login', () => {
    it('should POST credentials to /admin/login and store the cookie header', async () => {
      mockLoginPost.mockResolvedValue({
        data: { email: 'admin@example.com' },
        headers: { 'set-cookie': ['rf_admin_session=opaque-token; HttpOnly; Path=/'] },
      });

      await client.login();

      expect(mockLoginPost).toHaveBeenCalledWith('/admin/login', {
        email: 'admin@example.com',
        password: 'secret',
      });
      const created = (axios.create as jest.Mock).mock.results[0].value;
      expect(created.defaults.headers.common['Cookie']).toBe(
        'rf_admin_session=opaque-token'
      );
    });

    it('should throw a descriptive error on failure', async () => {
      mockLoginPost.mockRejectedValue(new Error('connect ECONNREFUSED'));

      await expect(client.login()).rejects.toThrow(
        'RouteForge admin login error: connect ECONNREFUSED'
      );
    });
  });

  describe('me', () => {
    it('should GET /admin/me and return the session', async () => {
      mockGet.mockResolvedValue({ data: { email: 'admin@example.com' } });

      const result = await client.me();

      expect(result).toEqual({ email: 'admin@example.com' });
      expect(mockGet).toHaveBeenCalledWith('/admin/me');
    });
  });

  describe('onboardModel', () => {
    it('should POST the model to /admin/infra/models', async () => {
      const model = makeOnboardModel();
      mockPost.mockResolvedValue({ data: { slug: model.slug } });

      const result = await client.onboardModel(model);

      expect(result).toEqual({ slug: model.slug });
      expect(mockPost).toHaveBeenCalledWith('/admin/infra/models', model);
    });
  });

  describe('editModel', () => {
    it('should PUT the model to /admin/infra/models/{slug}', async () => {
      const model = makeOnboardModel({ display_name: 'Llama 2 7B Updated' });
      mockPut.mockResolvedValue({ data: { slug: model.slug } });

      const result = await client.editModel('llama-2-7b', model);

      expect(result).toEqual({ slug: model.slug });
      expect(mockPut).toHaveBeenCalledWith('/admin/infra/models/llama-2-7b', model);
    });
  });

  describe('deleteModel', () => {
    it('should DELETE /admin/infra/models/{slug}', async () => {
      mockDelete.mockResolvedValue({ data: { deleted: true } });

      const result = await client.deleteModel('llama-2-7b');

      expect(result).toEqual({ deleted: true });
      expect(mockDelete).toHaveBeenCalledWith('/admin/infra/models/llama-2-7b');
    });

    it('should throw a descriptive error on failure', async () => {
      mockDelete.mockRejectedValue(new Error('404'));

      await expect(client.deleteModel('missing')).rejects.toThrow(
        'RouteForge admin delete model error: 404'
      );
    });
  });

  describe('listModels', () => {
    it('should GET /admin/infra/models and return the raw array', async () => {
      const models = [{ slug: 'llama-2-7b' }];
      mockGet.mockResolvedValue({ data: models });

      const result = await client.listModels();

      expect(result).toEqual(models);
      expect(mockGet).toHaveBeenCalledWith('/admin/infra/models');
    });
  });

  describe('applications', () => {
    it('should GET /admin/applications and return the raw array', async () => {
      const apps = [{ id: 'app-1', name: 'App One' }];
      mockGet.mockResolvedValue({ data: apps });

      const result = await client.listApplications();

      expect(result).toEqual(apps);
      expect(mockGet).toHaveBeenCalledWith('/admin/applications');
    });

    it('should POST to /admin/applications on createApplication', async () => {
      const app = { id: 'app-1', name: 'App One' };
      mockPost.mockResolvedValue({ data: app });

      const result = await client.createApplication(app);

      expect(result).toEqual(app);
      expect(mockPost).toHaveBeenCalledWith('/admin/applications', app);
    });

    it('should GET /admin/applications/{id} and return null on 404', async () => {
      mockGet.mockResolvedValue({ data: { id: 'app-1' } });
      expect(await client.getApplication('app-1')).toEqual({ id: 'app-1' });

      const error = Object.assign(new Error('404'), {
        isAxiosError: true,
        response: { status: 404 },
      });
      mockGet.mockRejectedValue(error);

      expect(await client.getApplication('missing')).toBeNull();
    });

    it('should PATCH /admin/applications/{id} on updateApplication', async () => {
      const update = { name: 'Renamed' };
      mockPatch.mockResolvedValue({ data: { id: 'app-1', name: 'Renamed' } });

      const result = await client.updateApplication('app-1', update);

      expect(result).toEqual({ id: 'app-1', name: 'Renamed' });
      expect(mockPatch).toHaveBeenCalledWith('/admin/applications/app-1', update);
    });
  });

  describe('createApplicationToken', () => {
    it('should POST {name: "default"} when no name is given', async () => {
      mockPost.mockResolvedValue({ data: { token: 'tok-1' } });

      await client.createApplicationToken('app-1');

      expect(mockPost).toHaveBeenCalledWith('/admin/applications/app-1/tokens', {
        name: 'default',
      });
    });

    it('should POST {name} when a name is given', async () => {
      mockPost.mockResolvedValue({ data: { token: 'tok-1' } });

      await client.createApplicationToken('app-1', 'ci-token');

      expect(mockPost).toHaveBeenCalledWith('/admin/applications/app-1/tokens', {
        name: 'ci-token',
      });
    });
  });

  describe('revokeToken', () => {
    it('should POST /admin/tokens/{id}/revoke', async () => {
      mockPost.mockResolvedValue({ data: { revoked: true } });

      const result = await client.revokeToken('tok-1');

      expect(result).toEqual({ revoked: true });
      expect(mockPost).toHaveBeenCalledWith('/admin/tokens/tok-1/revoke');
    });
  });

  describe('setPolicy', () => {
    it('should PUT the policy with null/undefined keys stripped', async () => {
      const policy: RouteForgePolicy = {
        allowed_tiers: ['small'],
        allowed_models: null,
        max_spend_usd_per_day: 10,
        max_cost_usd_per_request: undefined,
        residency: null,
      };
      mockPut.mockResolvedValue({ data: { ok: true } });

      const result = await client.setPolicy('app-1', policy);

      expect(result).toEqual({ ok: true });
      expect(mockPut).toHaveBeenCalledWith('/admin/applications/app-1/policy', {
        allowed_tiers: ['small'],
        max_spend_usd_per_day: 10,
      });
    });

    it('should throw a descriptive error on failure', async () => {
      mockPut.mockRejectedValue(new Error('nope'));

      await expect(client.setPolicy('app-1', {})).rejects.toThrow(
        'RouteForge admin set policy error: nope'
      );
    });
  });
});
