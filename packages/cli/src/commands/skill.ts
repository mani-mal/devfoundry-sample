import { Command } from 'commander';
import * as crypto from 'crypto';
import { DevFoundryCore } from '@dev-foundry/core';

export const createSkillCommand = (core?: DevFoundryCore) => {
  const skill = new Command('skill');

  skill
    .command('list')
    .description('List installed skills (from the Git-backed catalog)')
    .action(async () => {
      try {
        let rows: any[] = [];
        if (core) {
          const client = await core.getDatabase().pool.connect();
          try {
            const result = await client.query(
              'SELECT id, name, version, digest, approval_status FROM skills ORDER BY name'
            );
            rows = result.rows;
          } finally {
            client.release();
          }
        }

        console.log('Skills:');
        if (rows.length === 0) {
          console.log('  (no skills registered in the catalog)');
        }
        rows.forEach((row) => {
          console.log(
            `  - ${row.name}@${row.version} (${row.approval_status}) digest=${String(row.digest).substring(0, 12)}`
          );
        });
      } catch (error) {
        console.error(`Error listing skills: ${(error as Error).message}`);
        process.exit(1);
      }
    });

  skill
    .command('install')
    .description('Install a skill by ID into the Git-backed catalog')
    .argument('<skillId>', 'Skill ID')
    .option('--version <version>', 'Skill version', '1.0.0')
    .option('--git-repo <gitRepo>', 'Git repository URL', '')
    .option('--git-commit <gitCommit>', 'Git commit SHA', 'HEAD')
    .option('--path <path>', 'Skill path inside the repo', '')
    .option('--description <description>', 'Skill description', '')
    .option('--status <status>', 'Approval status (draft|approved|deprecated)', 'draft')
    .action(async (
      skillId: string,
      opts: { version: string; gitRepo: string; gitCommit: string; path: string; description: string; status: string }
    ) => {
      try {
        if (!core) {
          console.error('No database configured (set DATABASE_URL)');
          process.exit(1);
        }
        const digest = crypto
          .createHash('sha256')
          .update(`${skillId}@${opts.version}:${opts.gitRepo}:${opts.gitCommit}`)
          .digest('hex');

        const client = await core.getDatabase().pool.connect();
        try {
          const { rows } = await client.query(
            `
            INSERT INTO skills (version, digest, name, description, path, git_repository, git_commit, metadata, approval_status, approved_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, '{}'::jsonb, $8, CASE WHEN $8 = 'approved' THEN NOW() ELSE NULL END)
            ON CONFLICT (digest) DO UPDATE
              SET name = EXCLUDED.name,
                  description = EXCLUDED.description,
                  approval_status = EXCLUDED.approval_status,
                  updated_at = NOW()
            RETURNING id, name, version, approval_status
            `,
            [
              opts.version,
              digest,
              skillId,
              opts.description || null,
              opts.path || `/skills/${skillId}`,
              opts.gitRepo || 'unknown',
              opts.gitCommit,
              opts.status,
            ]
          );
          console.log(`Skill installed: ${rows[0].name}@${rows[0].version} (${rows[0].approval_status})`);
          console.log(`digest=${digest.substring(0, 12)} id=${rows[0].id}`);
        } finally {
          client.release();
        }
      } catch (error) {
        console.error(`Error installing skill: ${(error as Error).message}`);
        process.exit(1);
      }
    });

  return skill;
};
