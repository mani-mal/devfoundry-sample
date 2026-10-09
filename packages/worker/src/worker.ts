/**
 * OpenCode Worker Implementation
 * 
 * This worker uses OpenCode as the managed harness/agent execution environment.
 * OpenCode provides: Context-aware agent execution, tool calling,
 * workspace management, and session persistence.
 * 
 * DevFoundry Worker → OpenCode API → Agent execution
 */

import { OpenCodeAdapter } from './opencode';
import { RouteForgeClient } from '@dev-foundry/integrations-routeforge';
import { ContextForgeClient } from '@dev-foundry/integrations-context-forge';
import { Database } from '@dev-foundry/core';
import { Task, TaskPhase, TaskStatus } from '@dev-foundry/core';
import { createLogger } from '@dev-foundry/core';
import { v4 as uuidv4 } from 'uuid';

export interface WorkerOptions {
  database: Database;
  openCodeUrl: string;
  routeForgeUrl: string;
  contextForgeUrl: string;
  workerId: string;
}

export class DevFoundryWorker {
  private openCode: OpenCodeAdapter;
  private routeForge: RouteForgeClient;
  private contextForge: ContextForgeClient;
  private database: Database;
  private workerId: string;
  private logger = createLogger('worker');
  private running = false;

  constructor(options: WorkerOptions) {
    this.openCode = new OpenCodeAdapter({
      baseUrl: options.openCodeUrl,
    });
    this.routeForge = new RouteForgeClient({
      baseUrl: options.routeForgeUrl,
    });
    this.contextForge = new ContextForgeClient({
      baseUrl: options.contextForgeUrl,
    });
    this.database = options.database;
    this.workerId = options.workerId;
  }

  public async start(): Promise<void> {
    if (this.running) {
      this.logger.warn('Worker already running', { workerId: this.workerId });
      return;
    }

    this.running = true;
    this.logger.info('Worker started', { workerId: this.workerId });

    await this.pollTasks();
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
    const client = await this.database.pool.connect();
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
    this.logger.info('Running task phase', { taskId: task.id });

    // 1. Create OpenCode workspace
    const workspace = await this.openCode.createWorkspace({
      baseCommit: task.baseCommit,
      environment: {
        DATABASE_URL: process.env.DATABASE_URL || '',
        ROUTEFORGE_URL: process.env.ROUTEFORGE_URL || '',
        CONTEXFORGE_URL: process.env.CONTEXFORGE_URL || '',
      },
    });

    // 2. Create agent session with skills
    const session = await this.openCode.createSession({
      task: task.description,
      tools: task.skills,
      workspaceId: workspace.id,
    });

    // 3. Execute task with OpenCode
    const events = await this.openCode.sendInput(session.id, task.description);

    // 4. Collect patch from workspace
    const patch = await this.collectPatch(workspace.id);



    // 6. Store checkpoint
    const checkpoint = await this.openCode.createCheckpoint(session.id);

    await this.updateTaskStatus(task.id, 'Pending', 'Validating', undefined, {
      checkpoint: {
        snapshotId: checkpoint.snapshotId,
        workspaceState: checkpoint.workspaceState,
        sessionState: checkpoint.sessionState,
        timestamp: new Date(),
      },
    });
  }

  private async handleValidatingPhase(task: Task): Promise<void> {
    this.logger.info('Validating task', { taskId: task.id });

    // 1. Run build/lint checks
    const lintResults = await this.runLint(task);

    // 2. Run unit tests
    const testResults = await this.runTests(task);

    // 3. Run security checks
    const securityResults = await this.runSecurityScan(task);

    // 4. Collect evidence
    const evidence = [
      ...lintResults,
      ...testResults,
      ...securityResults,
    ];

    await this.storeEvidence(task.id, evidence);
    await this.updateTaskStatus(task.id, 'Pending', 'AwaitingReview', undefined);
  }

  private async handleAwaitingReviewPhase(task: Task): Promise<void> {
    this.logger.info('Awaiting review for task', { taskId: task.id });

    // 1. Generate review packet
    const reviewPacket = await this.generateReviewPacket(task);

    // 2. Store review packet
    await this.storeReviewPacket(task.id, reviewPacket);

    this.routeForge.createTrace('task-execution');

    // 4. Update task status
    await this.updateTaskStatus(task.id, 'Pending', 'Completed', undefined);
  }

  private async collectPatch(workspaceId: string): Promise<string> {
    // Collect file changes from checkpoint workspace state
    return '';
  }

  private async runLint(task: Task): Promise<any[]> {
    // Run linting on task changes
    return [];
  }

  private async runTests(task: Task): Promise<any[]> {
    // Run unit/integration tests
    return [];
  }

  private async runSecurityScan(task: Task): Promise<any[]> {
    // Run secret scanning and SAST
    return [];
  }

  private async storeEvidence(taskId: string, evidence: any[]): Promise<void> {
    // Store evidence in database
  }

  private async generateReviewPacket(task: Task): Promise<any> {
    // Generate review packet with all artifacts
    return {
      taskId: task.id,
      requirements: task.description,
      baseCommit: task.baseCommit,
      patchDigest: 'todo',
      changedFiles: [],
      skillVersions: task.skills,
      modelRoute: task.modelRoute,
      toolPermissions: task.toolPermissions,
      checkResults: [],
      environment: {},
      screenshots: [],
      knownGaps: [],
      failedAttempts: [],
    };
  }

  private async storeReviewPacket(taskId: string, packet: any): Promise<void> {
    // Store review packet in database
  }

  private async updateTaskStatus(
    taskId: string,
    status: TaskStatus,
    phase: TaskPhase,
    error?: Error,
    extraFields?: Record<string, unknown>
  ): Promise<void> {
    const client = await this.database.pool.connect();
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
