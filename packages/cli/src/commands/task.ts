import { Command } from 'commander';
import { DevFoundryCore } from '@dev-foundry/core';

export const createTaskCommand = (core: DevFoundryCore) => {
  const task = new Command('task');

  task
    .command('list')
    .description('List tasks')
    .option('--status <status>', 'Filter by status')
    .option('--phase <phase>', 'Filter by phase')
    .action(async (opts: { status?: string; phase?: string }) => {
      try {
        const client = await core.getDatabase().pool.connect();
        try {
          let query = 'SELECT id, status, phase, description, created_at FROM tasks';
          const params: any[] = [];
          const conditions: string[] = [];

          if (opts.status) {
            conditions.push('status = $' + (params.length + 1));
            params.push(opts.status);
          }
          if (opts.phase) {
            conditions.push('phase = $' + (params.length + 1));
            params.push(opts.phase);
          }

          if (conditions.length > 0) {
            query += ' WHERE ' + conditions.join(' AND ');
          }

          query += ' ORDER BY created_at DESC LIMIT 50';

          const result = await client.query(query, params);
          console.log('Tasks:');
          result.rows.forEach((row: any) => {
            console.log(
              `  - ${row.id}: ${row.description} (${row.status}, ${row.phase})`
            );
          });
        } finally {
          client.release();
        }
      } catch (error) {
        console.error(`Error listing tasks: ${(error as Error).message}`);
        process.exit(1);
      }
    });

  task
    .command('create')
    .description('Create a new task')
    .argument('<description>', 'Task description')
    .option('--project-id <projectId>', 'Project ID')
    .option('--user-id <userId>', 'User ID')
    .option('--model-route <modelRoute>', 'Model route')
    .action(async (description: string, opts: { projectId?: string; userId?: string; modelRoute?: string }) => {
      try {
        const client = await core.getDatabase().pool.connect();
        try {
          const { rows } = await client.query(
            `
            INSERT INTO tasks (id, tenant_id, project_id, user_id, status, phase, description, base_commit, target_branch, workspace_id, skills, context_ids, memory_ids, tool_permissions, model_route, capacity_profile, created_at, updated_at, retry_count)
            VALUES (gen_random_uuid(), gen_random_uuid(), $1, $2, 'Pending', 'Submitted', $3, 'HEAD', 'main', gen_random_uuid(), '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, $4, 'default', NOW(), NOW(), 0)
            RETURNING id, status, phase
            `,
            [
              opts.projectId || '00000000-0000-0000-0000-000000000000',
              opts.userId || '00000000-0000-0000-0000-000000000000',
              description,
              opts.modelRoute || 'default',
            ]
          );
          console.log(`Task created: ${rows[0].id}`);
          console.log(`Status: ${rows[0].status}`);
          console.log(`Phase: ${rows[0].phase}`);
        } finally {
          client.release();
        }
      } catch (error) {
        console.error(`Error creating task: ${(error as Error).message}`);
        process.exit(1);
      }
    });

  task
    .command('status')
    .description('Get task status')
    .argument('<taskId>', 'Task ID')
    .action(async (taskId: string) => {
      try {
        const client = await core.getDatabase().pool.connect();
        try {
          const { rows } = await client.query(
            `
            SELECT id, status, phase, description, created_at, started_at, completed_at, outcome
            FROM tasks
            WHERE id = $1
            `,
            [taskId]
          );

          if (rows.length === 0) {
            console.error(`Task not found: ${taskId}`);
            process.exit(1);
          }

          const task = rows[0];
          console.log(`Task: ${task.id}`);
          console.log(`Description: ${task.description}`);
          console.log(`Status: ${task.status}`);
          console.log(`Phase: ${task.phase}`);
          console.log(`Created: ${task.created_at}`);
          if (task.started_at) {
            console.log(`Started: ${task.started_at}`);
          }
          if (task.completed_at) {
            console.log(`Completed: ${task.completed_at}`);
          }
          if (task.outcome) {
            console.log(`Outcome: ${JSON.stringify(task.outcome, null, 2)}`);
          }
        } finally {
          client.release();
        }
      } catch (error) {
        console.error(`Error getting task status: ${(error as Error).message}`);
        process.exit(1);
      }
    });

  task
    .command('cancel')
    .description('Cancel a task')
    .argument('<taskId>', 'Task ID')
    .action(async (taskId: string) => {
      try {
        const client = await core.getDatabase().pool.connect();
        try {
          const { rows } = await client.query(
            `
            UPDATE tasks
            SET status = 'Cancelled',
                phase = 'Cancelled',
                updated_at = NOW(),
                outcome = jsonb_set(coalesce(outcome, '{}'::jsonb), '{success}', 'false'::jsonb) ||
                          jsonb_set(coalesce(outcome, '{}'::jsonb), '{reason}', '"Cancelled by user"'::jsonb)
            WHERE id = $1
            RETURNING id, status, phase
            `,
            [taskId]
          );

          if (rows.length === 0) {
            console.error(`Task not found: ${taskId}`);
            process.exit(1);
          }

          console.log(`Task cancelled: ${rows[0].id}`);
          console.log(`Status: ${rows[0].status}`);
          console.log(`Phase: ${rows[0].phase}`);
        } finally {
          client.release();
        }
      } catch (error) {
        console.error(`Error cancelling task: ${(error as Error).message}`);
        process.exit(1);
      }
    });

  return task;
};
