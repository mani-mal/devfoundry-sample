import { DevFoundryCore } from '@dev-foundry/core';
import { Task, TaskPhase, TaskStatus } from '@dev-foundry/core';
import { createLogger } from '@dev-foundry/core';

export interface WorkerOptions {
  core: DevFoundryCore;
  workerId: string;
}

export class DevFoundryWorker {
  private core: DevFoundryCore;
  private workerId: string;
  private logger = createLogger('worker');
  private running = false;
  private taskQueue: Task[] = [];

  constructor(options: WorkerOptions) {
    this.core = options.core;
    this.workerId = options.workerId;
  }

  public async start(): Promise<void> {
    if (this.running) {
      this.logger.warn('Worker already running', { workerId: this.workerId });
      return;
    }

    this.running = true;
    this.logger.info('Worker started', { workerId: this.workerId });

    this.pollTasks();
  }

  public async stop(): Promise<void> {
    if (!this.running) {
      this.logger.warn('Worker not running', { workerId: this.workerId });
      return;
    }

    this.running = false;
    this.logger.info('Worker stopped', { workerId: this.workerId });
  }

  private async pollTasks(): Promise<void> {
    if (!this.running) {
      return;
    }

    try {
      const tasks = await this.fetchPendingTasks();
      for (const task of tasks) {
        await this.processTask(task);
      }
    } catch (error) {
      this.logger.error('Error polling tasks', { workerId: this.workerId }, { error });
    }

    setTimeout(() => this.pollTasks(), 5000);
  }

  private async fetchPendingTasks(): Promise<Task[]> {
    const client = await this.core.getDatabase().pool.connect();
    try {
      const result = await client.query<Task>(
        `
        SELECT * FROM tasks 
        WHERE status = $1 AND phase = $2
        ORDER BY created_at ASC
        LIMIT 10
        `,
        ['Pending', 'Qualified']
      );
      return result.rows;
    } finally {
      client.release();
    }
  }

  private async processTask(task: Task): Promise<void> {
    this.logger.info('Processing task', {
      taskId: task.id,
      phase: task.phase,
      workerId: this.workerId,
    });

    try {
      await this.executeTask(task);
    } catch (error) {
      this.logger.error('Task failed', {
        taskId: task.id,
        error,
      });
      await this.updateTaskStatus(task.id, 'Failed', 'Failed', error as Error);
    }
  }

  private async executeTask(task: Task): Promise<void> {
    this.logger.info('Executing task', { taskId: task.id });

    switch (task.phase) {
      case 'Running':
        await this.handleRunningPhase(task);
        break;
      case 'Validating':
        await this.handleValidatingPhase(task);
        break;
      case 'AwaitingReview':
        await this.handleAwaitingReviewPhase(task);
        break;
      default:
        this.logger.warn('Unknown phase', {
          taskId: task.id,
          phase: task.phase,
        });
    }
  }

  private async handleRunningPhase(task: Task): Promise<void> {
    this.logger.info('Running task', { taskId: task.id });

    await this.updateTaskStatus(task.id, 'InProgress', 'Running', undefined, {
      startedAt: new Date(),
    });

    // TODO: Execute task with OpenCode adapter
    // TODO: Generate patch
    // TODO: Update checkpoint

    await this.updateTaskStatus(task.id, 'Pending', 'Validating', undefined, {
      completedAt: new Date(),
    });
  }

  private async handleValidatingPhase(task: Task): Promise<void> {
    this.logger.info('Validating task', { taskId: task.id });

    // TODO: Run build/lint
    // TODO: Run tests
    // TODO: Run security checks

    await this.updateTaskStatus(task.id, 'Pending', 'AwaitingReview', undefined);
  }

  private async handleAwaitingReviewPhase(task: Task): Promise<void> {
    this.logger.info('Awaiting review for task', { taskId: task.id });

    // TODO: Generate review packet
    // TODO: Store evidence
    // TODO: Update task status to Completed or Failed based on review
  }

  private async updateTaskStatus(
    taskId: string,
    status: TaskStatus,
    phase: TaskPhase,
    error?: Error,
    extraFields?: Record<string, unknown>
  ): Promise<void> {
    const client = await this.core.getDatabase().pool.connect();
    try {
      await client.query(
        `
        UPDATE tasks 
        SET status = $1, 
            phase = $2, 
            updated_at = NOW(),
            ${error ? 'outcome = $3,' : ''}
            ${extraFields ? this.buildExtraFieldsQuery(extraFields) : ''}
        WHERE id = $4
        `,
        [
          status,
          phase,
          error ? JSON.stringify({ success: false, reason: error.message }) : null,
          taskId,
          ...Object.values(extraFields || {}),
        ]
      );
    } finally {
      client.release();
    }
  }

  private buildExtraFieldsQuery(fields: Record<string, unknown>): string {
    return Object.keys(fields)
      .map((key) => `${key} = $${Object.keys(fields).length + 1}`)
      .join(', ');
  }
}
