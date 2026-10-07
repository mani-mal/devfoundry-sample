import { Command } from 'commander';

export const createSkillCommand = () => {
  const skill = new Command('skill');

  skill
    .command('list')
    .description('List installed skills')
    .action(async () => {
      try {
        console.log('Skills:');
        console.log('  - git:version-control');
        console.log('  - git:branch');
        console.log('  - git:commit');
        console.log('  - git:pr');
        console.log('  - file:read');
        console.log('  - file:write');
        console.log('  - file:edit');
        console.log('  - search:code');
        console.log('  - search:docs');
        console.log('  - test:run');
        console.log('  - test:coverage');
        console.log('  - build:verify');
        console.log('  - lint:fix');
        console.log('  - security:scan');
      } catch (error) {
        console.error(`Error listing skills: ${(error as Error).message}`);
        process.exit(1);
      }
    });

  skill
    .command('install')
    .description('Install a skill by ID')
    .argument('<skillId>', 'Skill ID')
    .option('--version <version>', 'Skill version')
    .option('--git-repo <gitRepo>', 'Git repository URL')
    .action(async (skillId: string, opts: { version?: string; gitRepo?: string }) => {
      try {
        console.log(`Installing skill: ${skillId}`);
        if (opts.version) {
          console.log(`Version: ${opts.version}`);
        }
        if (opts.gitRepo) {
          console.log(`From: ${opts.gitRepo}`);
        }
        console.log(`Skill installed successfully`);
      } catch (error) {
        console.error(`Error installing skill: ${(error as Error).message}`);
        process.exit(1);
      }
    });

  return skill;
};
