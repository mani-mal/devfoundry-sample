import { Command } from 'commander';
import { ContextForgeClient } from '@dev-foundry/integrations-context-forge';

export const createToolsCommand = (contextForge: ContextForgeClient) => {
  const tools = new Command('tools');

  tools
    .command('search')
    .description('Search for MCP tools by query')
    .argument('<query>', 'Search query')
    .action(async (query: string) => {
      try {
        const tools = await contextForge.listTools();
        const filtered = tools.filter(
          (tool) =>
            tool.name.toLowerCase().includes(query.toLowerCase()) ||
            (tool.description ?? '').toLowerCase().includes(query.toLowerCase())
        );
        console.log('Found tools:');
        filtered.forEach((tool) => {
          console.log(`  - ${tool.id}: ${tool.name}`);
          console.log(`    ${tool.description}`);
        });
      } catch (error) {
        console.error(`Error searching tools: ${(error as Error).message}`);
        process.exit(1);
      }
    });

  tools
    .command('describe')
    .description('Describe a tool by ID')
    .argument('<toolId>', 'Tool ID')
    .action(async (toolId: string) => {
      try {
        const tool = await contextForge.getTool(toolId);
        if (!tool) {
          console.error(`Tool not found: ${toolId}`);
          process.exit(1);
        }
        console.log(`Tool: ${tool.name}`);
        console.log(`ID: ${tool.id}`);
        console.log(`Description: ${tool.description}`);
        console.log(`Enabled: ${tool.enabled}`);
        console.log(`Scopes: ${tool.scopes.join(', ')}`);
        console.log(`Schema: ${JSON.stringify(tool.schema, null, 2)}`);
      } catch (error) {
        console.error(`Error describing tool: ${(error as Error).message}`);
        process.exit(1);
      }
    });

  tools
    .command('call')
    .description('Call a tool with input JSON')
    .argument('<toolId>', 'Tool ID')
    .argument('<input>', 'Input JSON string')
    .action(async (toolId: string, input: string) => {
      try {
        let inputObj: Record<string, unknown>;
        try {
          inputObj = JSON.parse(input);
        } catch {
          console.error('Invalid JSON input');
          process.exit(1);
        }
        const result = await contextForge.callTool(toolId, inputObj);
        console.log(JSON.stringify(result, null, 2));
      } catch (error) {
        console.error(`Error calling tool: ${(error as Error).message}`);
        process.exit(1);
      }
    });

  return tools;
};
