import { Command } from 'commander';
import * as fs from 'fs';
import * as path from 'path';

function configDir(): string {
  return path.join(process.cwd(), '.devfoundry');
}

function configFile(): string {
  return path.join(configDir(), 'config.json');
}

function readConfig(): Record<string, string> {
  try {
    return JSON.parse(fs.readFileSync(configFile(), 'utf8'));
  } catch {
    return {};
  }
}

function writeConfig(config: Record<string, string>): void {
  fs.mkdirSync(configDir(), { recursive: true });
  fs.writeFileSync(configFile(), JSON.stringify(config, null, 2) + '\n');
}

export const createConfigCommand = () => {
  const config = new Command('config');

  config
    .command('get')
    .description('Get configuration value (env fallback, then .devfoundry/config.json)')
    .argument('<key>', 'Configuration key')
    .action(async (key: string) => {
      try {
        const envKey = `DEVFOUNDRY_${key.toUpperCase().replace(/\./g, '_')}`;
        const persisted = readConfig()[key];
        const value = process.env[envKey] ?? persisted;
        if (value === undefined) {
          console.error(`Configuration key not found: ${key}`);
          process.exit(1);
        }
        console.log(value);
      } catch (error) {
        console.error(`Error getting config: ${(error as Error).message}`);
        process.exit(1);
      }
    });

  config
    .command('set')
    .description('Set configuration value (persist to .devfoundry/config.json)')
    .argument('<key>', 'Configuration key')
    .argument('<value>', 'Configuration value')
    .action(async (key: string, value: string) => {
      try {
        const config = readConfig();
        config[key] = value;
        writeConfig(config);
        console.log(`Set ${key}=${value}`);
        console.log(`Persisted to ${configFile()}`);
      } catch (error) {
        console.error(`Error setting config: ${(error as Error).message}`);
        process.exit(1);
      }
    });

  config
    .command('list')
    .description('List all persisted configuration keys')
    .action(async () => {
      try {
        const persisted = readConfig();
        const keys = Object.keys(persisted);
        if (keys.length === 0) {
          console.log('(no persisted configuration)');
          return;
        }
        console.log('Persisted configuration:');
        keys.forEach((k) => console.log(`  ${k}=${persisted[k]}`));
      } catch (error) {
        console.error(`Error listing config: ${(error as Error).message}`);
        process.exit(1);
      }
    });

  return config;
};
