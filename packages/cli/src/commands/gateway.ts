import { Command } from 'commander';
import axios from 'axios';

const errorMessage = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { error?: string } | undefined)?.error;
    return detail ? `${error.message}: ${detail}` : error.message;
  }
  return (error as Error).message;
};

const splitList = (value: string) =>
  value
    .split(',')
    .map((v) => v.trim())
    .filter(Boolean);

const parseNumber = (value: string, label: string): number => {
  const num = Number(value);
  if (Number.isNaN(num)) {
    console.error(`${label} must be a number`);
    process.exit(1);
  }
  return num;
};

export const createGatewayCommand = (baseUrl: string) => {
  const api = axios.create({
    baseURL: baseUrl,
    timeout: 30000,
    headers: { 'Content-Type': 'application/json' },
  });

  const gateway = new Command('gateway');

  gateway
    .command('apps')
    .description('List gateway applications')
    .action(async () => {
      try {
        const response = await api.get('/api/gateway/applications');
        const apps: any[] = response.data?.applications ?? [];
        console.log('Applications:');
        if (apps.length === 0) {
          console.log('  (no applications registered)');
          return;
        }
        apps.forEach((app: any) => {
          console.log(`  - ${app.id}: ${app.name} (${app.status ?? 'unknown'})`);
          if (app.owner_email) {
            console.log(`    owner: ${app.owner_email}`);
          }
          if (app.policy) {
            console.log(`    policy: ${JSON.stringify(app.policy)}`);
          }
        });
      } catch (error) {
        console.error(`Error listing applications: ${errorMessage(error)}`);
        process.exit(1);
      }
    });

  gateway
    .command('create-app')
    .description('Register a gateway application')
    .argument('<id>', 'Application ID')
    .argument('<name>', 'Application name')
    .option('--owner-email <email>', 'Owner email')
    .action(async (id: string, name: string, opts: { ownerEmail?: string }) => {
      try {
        const body: Record<string, unknown> = { id, name };
        if (opts.ownerEmail !== undefined) body.ownerEmail = opts.ownerEmail;
        const response = await api.post('/api/gateway/applications', body);
        console.log(`Application created: ${id}`);
        console.log(JSON.stringify(response.data, null, 2));
      } catch (error) {
        console.error(`Error creating application: ${errorMessage(error)}`);
        process.exit(1);
      }
    });

  gateway
    .command('create-token')
    .description('Create an application token')
    .argument('<appId>', 'Application ID')
    .option('--name <name>', 'Token name', 'default')
    .action(async (appId: string, opts: { name: string }) => {
      try {
        const response = await api.post(`/api/gateway/applications/${appId}/tokens`, { name: opts.name });
        console.log(`Token created for ${appId}:`);
        console.log(JSON.stringify(response.data, null, 2));
        console.log('Copy now — shown once.');
      } catch (error) {
        console.error(`Error creating token: ${errorMessage(error)}`);
        process.exit(1);
      }
    });

  gateway
    .command('revoke-token')
    .description('Revoke an application token')
    .argument('<tokenId>', 'Token ID')
    .action(async (tokenId: string) => {
      try {
        const response = await api.post(`/api/gateway/tokens/${tokenId}/revoke`);
        console.log(`Token revoked: ${tokenId}`);
        console.log(JSON.stringify(response.data, null, 2));
      } catch (error) {
        console.error(`Error revoking token: ${errorMessage(error)}`);
        process.exit(1);
      }
    });

  gateway
    .command('policy')
    .description('Set the routing policy for an application')
    .argument('<appId>', 'Application ID')
    .option('--tiers <tiers>', 'Allowed tiers (comma-separated)')
    .option('--providers <providers>', 'Allowed providers (comma-separated)')
    .option('--models <models>', 'Allowed models (comma-separated)')
    .option('--residency <residency>', 'Residency')
    .option('--max-spend-per-day <usd>', 'Max spend (USD/day)')
    .option('--max-cost-per-request <usd>', 'Max cost (USD/request)')
    .action(async (
      appId: string,
      opts: {
        tiers?: string;
        providers?: string;
        models?: string;
        residency?: string;
        maxSpendPerDay?: string;
        maxCostPerRequest?: string;
      }
    ) => {
      try {
        const body: Record<string, unknown> = {};
        if (opts.tiers !== undefined) body.allowedTiers = splitList(opts.tiers);
        if (opts.providers !== undefined) body.allowedProviders = splitList(opts.providers);
        if (opts.models !== undefined) body.allowedModels = splitList(opts.models);
        if (opts.residency !== undefined) body.residency = opts.residency;
        if (opts.maxSpendPerDay !== undefined) body.maxSpendUsdPerDay = parseNumber(opts.maxSpendPerDay, 'maxSpendUsdPerDay');
        if (opts.maxCostPerRequest !== undefined) body.maxCostUsdPerRequest = parseNumber(opts.maxCostPerRequest, 'maxCostUsdPerRequest');
        const response = await api.put(`/api/gateway/applications/${appId}/policy`, body);
        console.log(`Policy updated for ${appId}`);
        console.log(JSON.stringify(response.data, null, 2));
      } catch (error) {
        console.error(`Error setting policy: ${errorMessage(error)}`);
        process.exit();
      }
    });

  return gateway;
};
