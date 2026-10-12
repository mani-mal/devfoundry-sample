#!/usr/bin/env node

import { Command } from 'commander';
import { DevFoundryCore } from '@dev-foundry/core';
import { ContextForgeClient } from '@dev-foundry/integrations-context-forge';
import { createToolsCommand } from './commands/tools.js';
import { createTaskCommand } from './commands/task.js';
import { createSkillCommand } from './commands/skill.js';
import { createConfigCommand } from './commands/config.js';
import { createModelsCommand } from './commands/models.js';
import { createGatewayCommand } from './commands/gateway.js';

const program = new Command();

const DATABASE_URL = process.env.DATABASE_URL || 'postgres://devfoundry:devfoundry@localhost:5432/devfoundry';
const ROUTEFORGE_URL = process.env.ROUTEFORGE_URL || 'http://localhost:8000';
const CONTEXTFORGE_URL = process.env.CONTEXTFORGE_URL || 'http://localhost:8001';
const DEVFOUNDRY_URL = process.env.DEVFOUNDRY_URL || 'http://localhost:3000';

const core = new DevFoundryCore({
  databaseUrl: DATABASE_URL,
  routeForgeUrl: ROUTEFORGE_URL,
});

const contextForge = new ContextForgeClient({
  baseUrl: CONTEXTFORGE_URL,
});

program
  .name('devfoundry')
  .description('DevFoundry CLI - on-premises software factory')
  .version('0.1.0');

program.addCommand(createToolsCommand(contextForge));
program.addCommand(createTaskCommand(core));
program.addCommand(createSkillCommand(core));
program.addCommand(createConfigCommand());
program.addCommand(createModelsCommand(DEVFOUNDRY_URL));
program.addCommand(createGatewayCommand(DEVFOUNDRY_URL));

program
  .command('health')
  .description('Check DevFoundry health')
  .action(async () => {
    try {
      console.log('Checking DevFoundry health...');
      
      const dbClient = await core.getDatabase().pool.connect();
      try {
        await dbClient.query('SELECT 1');
        console.log('Database: OK');
      } finally {
        dbClient.release();
      }

      const contextForgeHealthy = await contextForge.healthCheck();
      console.log(`ContextForge: ${contextForgeHealthy ? 'OK' : 'FAIL'}`);

      console.log('DevFoundry: healthy');
    } catch (error) {
      console.error(`Health check failed: ${(error as Error).message}`);
      process.exit(1);
    }
  });

program.parse(process.argv);
