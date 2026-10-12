import { Command } from 'commander';
import axios from 'axios';

interface ModelFieldOptions {
  displayName?: string;
  tier?: string;
  endpoint?: string;
  priceInput?: string;
  priceOutput?: string;
  contextWindow?: string;
  notes?: string;
}

const errorMessage = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { error?: string } | undefined)?.error;
    return detail ? `${error.message}: ${detail}` : error.message;
  }
  return (error as Error).message;
};

const parseNumber = (value: string, label: string): number => {
  const num = Number(value);
  if (Number.isNaN(num)) {
    console.error(`${label} must be a number`);
    process.exit(1);
  }
  return num;
};

const omitMissing = (obj: Record<string, unknown>) =>
  Object.fromEntries(Object.entries(obj).filter(([, v]) => v !== undefined && v !== null && v !== ''));

const modelBody = (model: any, opts: ModelFieldOptions): Record<string, unknown> =>
  omitMissing({
    slug: model.slug,
    displayName: opts.displayName ?? model.display_name,
    tier: opts.tier ?? model.tier,
    endpoint: opts.endpoint ?? model.endpoint,
    priceInput: opts.priceInput !== undefined ? Number(opts.priceInput) : model.price_input,
    priceOutput: opts.priceOutput !== undefined ? Number(opts.priceOutput) : model.price_output,
    priceCachedInput: model.price_cached_input,
    quality: model.quality,
    contextWindow: opts.contextWindow !== undefined ? Number(opts.contextWindow) : model.context_window,
    allowedAppIds: model.allowed_app_ids,
    notes: opts.notes ?? model.notes,
    enabled: model.enabled,
    region: model.region,
    promptRetention: model.prompt_retention,
    acceptsRawSensitive: model.accepts_raw_sensitive,
  });

export const createModelsCommand = (baseUrl: string) => {
  const api = axios.create({
    baseURL: baseUrl,
    timeout: 30000,
    headers: { 'Content-Type': 'application/json' },
  });

  const listModels = async (): Promise<any[]> => {
    const response = await api.get('/api/gateway/models');
    return response.data?.models ?? [];
  };

  const findModel = async (slug: string): Promise<any | undefined> => {
    const models = await listModels();
    return models.find((m: any) => m.slug === slug);
  };

  const models = new Command('models');

  models
    .command('list')
    .description('List onboarded models')
    .action(async () => {
      try {
        const items = await listModels();
        console.log('Models:');
        if (items.length === 0) {
          console.log('  (no models onboarded)');
          return;
        }
        const headers = ['SLUG', 'TIER', 'ENDPOINT', 'ENABLED', 'CONTEXT', 'PRICE IN/OUT'];
        const rows = items.map((m: any) => [
          String(m.slug ?? ''),
          String(m.tier ?? ''),
          String(m.endpoint ?? ''),
          m.enabled ? 'true' : 'false',
          m.context_window != null ? String(m.context_window) : '-',
          `${m.price_input ?? '-'}/${m.price_output ?? '-'}`,
        ]);
        const widths = headers.map((h, i) => Math.max(h.length, ...rows.map((r) => r[i].length)));
        const line = (cells: string[]) => cells.map((c, i) => c.padEnd(widths[i])).join('  ');
        console.log(line(headers));
        rows.forEach((r) => console.log(line(r)));
      } catch (error) {
        console.error(`Error listing models: ${errorMessage(error)}`);
        process.exit(1);
      }
    });

  models
    .command('onboard')
    .description('Onboard a model to the gateway')
    .argument('<slug>', 'Model slug')
    .option('--display-name <name>', 'Display name')
    .option('--tier <tier>', 'Model tier (cheap|mid|frontier)', 'mid')
    .option('--endpoint <endpoint>', 'Model endpoint URL', 'http://routeforge:8000/v1')
    .option('--price-input <usd>', 'Price input ($/M tokens)', '0')
    .option('--price-output <usd>', 'Price output ($/M tokens)', '0')
    .option('--context-window <tokens>', 'Context window size')
    .option('--notes <notes>', 'Notes')
    .action(async (slug: string, opts: ModelFieldOptions) => {
      try {
        const priceInput = parseNumber(opts.priceInput ?? '0', 'priceInput');
        const priceOutput = parseNumber(opts.priceOutput ?? '0', 'priceOutput');
        const body = omitMissing({
          slug,
          displayName: opts.displayName || slug,
          tier: opts.tier,
          endpoint: opts.endpoint,
          priceInput,
          priceOutput,
          contextWindow: opts.contextWindow !== undefined ? parseNumber(opts.contextWindow, 'contextWindow') : undefined,
          notes: opts.notes,
        });
        const response = await api.post('/api/gateway/models', body);
        console.log(`Model onboarded: ${slug}`);
        console.log(JSON.stringify(response.data, null, 2));
      } catch (error) {
        console.error(`Error onboarding model: ${errorMessage(error)}`);
        process.exit(1);
      }
    });

  models
    .command('edit')
    .description('Edit an onboarded model')
    .argument('<slug>', 'Model slug')
    .option('--display-name <name>', 'Display name')
    .option('--tier <tier>', 'Model tier (cheap|mid|frontier)')
    .option('--endpoint <endpoint>', 'Model endpoint URL')
    .option('--price-input <usd>', 'Price input ($/M tokens)')
    .option('--price-output <usd>', 'Price output ($/M tokens)')
    .option('--context-window <tokens>', 'Context window size')
    .option('--notes <notes>', 'Notes')
    .action(async (slug: string, opts: ModelFieldOptions) => {
      try {
        const model = await findModel(slug);
        if (!model) {
          console.error(`Model not found: ${slug}`);
          process.exit(1);
        }
        if (opts.priceInput !== undefined) parseNumber(opts.priceInput, 'priceInput');
        if (opts.priceOutput !== undefined) parseNumber(opts.priceOutput, 'priceOutput');
        if (opts.contextWindow !== undefined) parseNumber(opts.contextWindow, 'contextWindow');
        const response = await api.put(`/api/gateway/models/${slug}`, modelBody(model, opts));
        console.log(`Model updated: ${slug}`);
        console.log(JSON.stringify(response.data, null, 2));
      } catch (error) {
        console.error(`Error editing model: ${errorMessage(error)}`);
        process.exit(1);
      }
    });

  models
    .command('delete')
    .description('Delete an onboarded model')
    .argument('<slug>', 'Model slug')
    .action(async (slug: string) => {
      try {
        await api.delete(`/api/gateway/models/${slug}`);
        console.log(`Model deleted: ${slug}`);
      } catch (error) {
        console.error(`Error deleting model: ${errorMessage(error)}`);
        process.exit(1);
      }
    });

  const setEnabled = async (slug: string, enabled: boolean) => {
    const model = await findModel(slug);
    if (!model) {
      console.error(`Model not found: ${slug}`);
      process.exit(1);
    }
    const body = modelBody(model, {});
    body.enabled = enabled;
    await api.put(`/api/gateway/models/${slug}`, body);
    console.log(`Model ${slug} ${enabled ? 'enabled' : 'disabled'}`);
  };

  models
    .command('enable')
    .description('Enable a model')
    .argument('<slug>', 'Model slug')
    .action(async (slug: string) => {
      try {
        await setEnabled(slug, true);
      } catch (error) {
        console.error(`Error enabling model: ${errorMessage(error)}`);
        process.exit(1);
      }
    });

  models
    .command('disable')
    .description('Disable a model')
    .argument('<slug>', 'Model slug')
    .action(async (slug: string) => {
      try {
        await setEnabled(slug, false);
      } catch (error) {
        console.error(`Error disabling model: ${errorMessage(error)}`);
        process.exit(1);
      }
    });

  return models;
};
