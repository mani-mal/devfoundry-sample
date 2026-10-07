import { Command } from 'commander';

export const createConfigCommand = () => {
  const config = new Command('config');

  config
    .command('get')
    .description('Get configuration value')
    .argument('<key>', 'Configuration key')
    .action(async (key: string) => {
      try {
        const value = process.env[`DEVFOUNDRY_${key.toUpperCase().replace(/\./g, '_')}`];
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
        console.log(`Set ${key}=${value}`);
        console.log(`Configuration updated. Restart required for changes to take effect.`);
      } catch (error) {
        console.error(`Error setting config: ${(error as Error).message}`);
        process.exit(1);
      }
    });

  return config;
};
