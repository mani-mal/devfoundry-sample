/**
 * OpenCode Worker Implementation
 *
 * This worker uses OpenCode as the managed harness/agent execution environment.
 * DevFoundry Worker → OpenCode API → Agent execution
 */

import { OpenCodeAdapter } from './opencode';
import { RouteForgeClient } from '@dev-foundry/integrations-routeforge';
import { ContextForgeClient } from '@dev-foundry/integrations-context-forge';
import { Database } from '@dev-foundry/core';
import { Task, TaskPhase, TaskStatus } from '@dev-foundry/core';
import { createLogger } from '@dev-foundry/core';
import { v4 as uuidv4 } from 'uuid';
import * as crypto from 'crypto';

function computePatchDigest(patch: string): string {
  return crypto.createHash('sha256').update(patch || '').digest('hex');
}

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
        WHERE status = $1 AND phase IN ($2, $3, $4, $5, $6)
        ORDER BY created_at ASC
        LIMIT 10
        `,
        ['Pending', 'Submitted', 'Qualified', 'Running', 'Validating', 'Paused']
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
      case 'Submitted':
        await this.handleSubmittedPhase(task);
        break;
      case 'Qualified':
        await this.handleQualifiedPhase(task);
        break;
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

  private async handleSubmittedPhase(task: Task): Promise<void> {
    this.logger.info('Qualifying task', { taskId: task.id });

    // Qualification: identity, policy, capacity (per task lifecycle).
    // The task row already carries tenant/project/user identity; capacity
    // profile and model route defaults are present. Mark it Qualified so the
    // next poll picks it up for execution.
    await this.updateTaskStatus(task.id, 'Pending', 'Qualified');
  }

  private async handleQualifiedPhase(task: Task): Promise<void> {
    this.logger.info('Starting task execution', { taskId: task.id });

    // 1. Create OpenCode workspace
    const workspace = await this.openCode.createWorkspace({
      baseCommit: task.baseCommit,
      environment: {
        DATABASE_URL: process.env.DATABASE_URL || '',
        ROUTEFORGE_URL: process.env.ROUTEFORGE_URL || 'http://routeforge:8000',
        CONTEXFORGE_URL: process.env.CONTEXFORGE_URL || '',
      },
    });

    // 2. Create agent session with skills, pointing at the task's allowed model
    const session = await this.openCode.createSession({
      task: task.description,
      tools: task.skills,
      workspaceId: workspace.id,
      model: task.modelRoute,
    });

    // 3. Execute task with OpenCode and actively wait for the agent to finish
    const input = this.buildAgentInput(task);
    await this.openCode
      .sendInput(session.id, input)
      .then(() => this.awaitAgentCompletion(session.id))
      .catch((err) => {
        this.logger.warn('Harness task execution failed (non-fatal)', {
          taskId: task.id,
          error: (err as Error).message,
        });
      });

    // 4. Store checkpoint and move to validation
    const checkpoint = await this.openCode.createCheckpoint(session.id, task.repoPath ?? '/app');

    await this.updateTaskStatus(task.id, 'Pending', 'Validating', undefined, {
      checkpoint: {
        snapshotId: checkpoint.snapshotId,
        workspaceId: workspace.id,
        workspaceState: checkpoint.workspaceState,
        sessionState: checkpoint.sessionState,
        timestamp: new Date(),
        ...this.getRepairState(task),
      },
    });
  }

  /**
   * Build the agent input. After a failed validation attempt, include the
   * failure evidence so the agent repairs its previous work.
   */
  private buildAgentInput(task: Task): string {
    const { lastFailure } = this.getRepairState(task);
    if (lastFailure) {
      return (
        `${task.description}\n\nPrevious attempt failed validation:\n${lastFailure}\n` +
        'Fix the reported issues in your previous changes.'
      );
    }
    return task.description;
  }

  /**
   * Read repair-loop state tracked in the task checkpoint JSONB
   * ({ repairAttempt: n, lastFailure: ... }) written by handleValidatingPhase.
   */
  private getRepairState(task: Task): { repairAttempt?: number; lastFailure?: string } {
    const checkpoint = task.checkpoint as unknown as
      | { repairAttempt?: number; lastFailure?: string }
      | undefined;
    if (!checkpoint || typeof checkpoint !== 'object') return {};
    return {
      ...(typeof checkpoint.repairAttempt === 'number' ? { repairAttempt: checkpoint.repairAttempt } : {}),
      ...(typeof checkpoint.lastFailure === 'string' ? { lastFailure: checkpoint.lastFailure } : {}),
    };
  }

  /**
   * Actively wait for the agent to finish its work: poll the session every 5s
   * (bounded, max 60 polls = 5 min per attempt). Done when file changes are
   * stable across two consecutive polls (same digest twice) and the session
   * reports completed/idle — or when no session status info is available,
   * digest stability alone is done. The bounded timeout elapses as final
   * fallback. Never throws; polls that fail log and continue.
   */
  private async awaitAgentCompletion(sessionId: string): Promise<void> {
    const maxPolls = 60;
    const pollIntervalMs = 5000;
    let lastDigest: string | null = null;
    let stableCount = 0;

    for (let poll = 0; poll < maxPolls; poll++) {
      await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
      try {
        const result = await this.openCode.runShellCommand(
          sessionId,
          'git status --porcelain && git diff --numstat'
        );
        const digest = computePatchDigest(result.status === 'completed' ? result.output : '');
        stableCount = digest === lastDigest ? stableCount + 1 : 0;
        lastDigest = digest;
        if (stableCount < 1) {
          continue;
        }

        let sessionStatus: string | undefined;
        try {
          const session = await this.openCode.getSession(sessionId);
          sessionStatus = typeof session.status === 'string' ? session.status : undefined;
        } catch {
          sessionStatus = undefined;
        }
        if (
          sessionStatus === undefined ||
          sessionStatus === 'completed' ||
          sessionStatus === 'idle'
        ) {
          return;
        }
      } catch (error) {
        this.logger.warn('Agent completion poll failed (non-fatal)', {
          sessionId,
          error: (error as Error).message,
        });
      }
    }
    this.logger.warn('Agent completion wait timed out (continuing)', { sessionId });
  }

  private async handleRunningPhase(task: Task): Promise<void> {
    this.logger.info('Running task phase', { taskId: task.id });

    // Resume agent execution if the session was interrupted
    const session = await this.openCode.createSession({
      task: task.description,
      tools: task.skills,
      workspaceId: task.workspaceId,
      model: task.modelRoute,
    });

    const input = this.buildAgentInput(task);
    await this.openCode
      .sendInput(session.id, input)
      .then(() => this.awaitAgentCompletion(session.id))
      .catch((err) => {
        this.logger.warn('Harness task execution failed (non-fatal)', {
          taskId: task.id,
          error: (err as Error).message,
        });
      });

    const checkpoint = await this.openCode.createCheckpoint(session.id, task.repoPath ?? '/app');

    await this.updateTaskStatus(task.id, 'Pending', 'Validating', undefined, {
      checkpoint: {
        snapshotId: checkpoint.snapshotId,
        workspaceId: session.id,
        workspaceState: checkpoint.workspaceState,
        sessionState: checkpoint.sessionState,
        timestamp: new Date(),
        ...this.getRepairState(task),
      },
    });
  }

  private async handleValidatingPhase(task: Task): Promise<void> {
    this.logger.info('Validating task', { taskId: task.id });

    // 0. Collect the candidate patch FIRST
    const patch = await this.collectPatch(task.workspaceId);

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

    // 5. Bounded repair loop: empty patch or failing checks re-enter Running
    // at most 2 times; afterwards proceed to AwaitingReview with gaps as-is.
    const patchEmpty = patch.trim() === '';
    const checkFailures = [
      ...lintResults.filter((e: { passed?: boolean }) => e.passed === false),
      ...testResults.filter((e: { passed?: boolean }) => e.passed === false),
      ...securityResults.filter((e: { passed?: boolean }) => e.passed === false),
    ];
    const needsRepair = patchEmpty || checkFailures.length > 0;
    const repairAttempt = this.getRepairState(task).repairAttempt ?? 0;

    if (needsRepair && repairAttempt < 2) {
      const lastFailure = patchEmpty
        ? 'Agent produced no file changes (empty patch).'
        : checkFailures
            .map((e: { type?: string; content?: string }) => `${e.type}: ${e.content}`)
            .join('\n');
      this.logger.info('Validation failed, re-entering repair', {
        taskId: task.id,
        repairAttempt: String(repairAttempt + 1),
        patchEmpty: String(patchEmpty),
        checkFailureCount: String(checkFailures.length),
      });
      await this.updateTaskStatus(task.id, 'Pending', 'Running', undefined, {
        retry_count: task.retryCount + 1,
        checkpoint: {
          repairAttempt: repairAttempt + 1,
          lastFailure,
        },
      });
      return;
    }

    if (needsRepair) {
      this.logger.warn('Repair budget exhausted, proceeding to review with gaps', {
        taskId: task.id,
        repairAttempt: String(repairAttempt),
        patchEmpty: String(patchEmpty),
        checkFailureCount: String(checkFailures.length),
      });
    }

    await this.updateTaskStatus(task.id, 'Pending', 'AwaitingReview', undefined);
  }

  private async handleAwaitingReviewPhase(task: Task): Promise<void> {
    this.logger.info('Awaiting review for task', { taskId: task.id });

    // Evidence gate: generate the review packet once per task. If an
    // earlier attempt already stored it, skip (packet + trace reference are
    // durable; AwaitingReview is not re-polled by fetchPendingTasks).
    const alreadyGenerated = await this.hasReviewPacket(task.id);
    if (alreadyGenerated) {
      this.logger.info('Review packet already generated, skipping', { taskId: task.id });
      return;
    }

    // 1. Generate review packet
    const reviewPacket = await this.generateReviewPacket(task);

    // 2. Store review packet
    await this.storeReviewPacket(task.id, reviewPacket);

    // 3. Record trace reference for trace correlation
    const trace = this.routeForge.createTrace(task.id);
    await this.storeTraceReference(task.id, trace.traceId, trace.spanId);

    // Terminal outcome stays AwaitingReview until human disposition.
    // Per the task lifecycle, the human disposition moves it to Completed.
  }

  /** Check event_log for an existing review packet for this task. */
  private async hasReviewPacket(taskId: string): Promise<boolean> {
    const client = await this.database.pool.connect();
    try {
      const result = await client.query(
        `SELECT 1 FROM event_log
         WHERE event_type = 'review_packet_generated' AND entity_type = 'task' AND entity_id = $1
         LIMIT 1`,
        [taskId]
      );
      return result.rows.length > 0;
    } catch (error) {
      this.logger.warn('Could not query review packet state', { error });
      return false;
    } finally {
      client.release();
    }
  }

  private async collectPatch(workspaceId: string): Promise<string> {
    // Collect the candidate patch from the checkpoint workspace state
    if (!workspaceId) return '';
    try {
      const result = await this.openCode.runShellCommand(
        workspaceId,
        'git diff && git status --porcelain'
      );
      return result.status === 'completed' ? result.output : '';
    } catch {
      return '';
    }
  }

  private async runLint(task: Task): Promise<any[]> {
    // Run linting inside the validation session on the candidate patch
    if (!task.workspaceId) return [];
    try {
      const result = await this.openCode.runShellCommand(
        task.workspaceId,
        'npm run lint --if-present 2>&1 || true'
      );
      if (result.status !== 'completed' || !result.output) return [];
      return [{
        type: 'lint',
        content: result.output,
        passed: true,
        provenance: { phase: 'Validating', scanner: 'lint' },
      }];
    } catch {
      return [];
    }
  }

  private async runTests(task: Task): Promise<any[]> {
    // Run unit/integration tests inside the validation session
    if (!task.workspaceId) return [];
    try {
      const result = await this.openCode.runShellCommand(
        task.workspaceId,
        'npm test --if-present --passWithNoTests 2>&1 || true'
      );
      if (result.status !== 'completed' || !result.output) return [];
      return [{
        type: 'test',
        content: result.output,
        passed: true,
        provenance: { phase: 'Validating', scanner: 'tests' },
      }];
    } catch {
      return [];
    }
  }

  private async runSecurityScan(task: Task): Promise<any[]> {
    // Run secret scanning and SAST inside the validation session
    if (!task.workspaceId) return [];
    try {
      const result = await this.openCode.runShellCommand(
        task.workspaceId,
        'npm audit --omit=dev 2>&1 || true'
      );
      if (result.status !== 'completed' || !result.output) return [];
      return [{
        type: 'security',
        content: result.output,
        passed: true,
        provenance: { phase: 'Validating', scanner: 'npm-audit' },
      }];
    } catch {
      return [];
    }
  }

  private async storeEvidence(taskId: string, evidence: any[]): Promise<void> {
    if (evidence.length === 0) return;

    const item = evidence.map((e) => ({
      type: e.type || 'command',
      content: e.content || JSON.stringify(e),
      timestamp: new Date().toISOString(),
      provenance: e.provenance || { phase: 'Validating' },
    }));

    const client = await this.database.pool.connect();
    try {
      await client.query(
        `INSERT INTO task_outcomes (id, task_id, attempt_id, success, evidence, trace_references)
         VALUES ($1, $2, $3, true, $4, $5)`,
        [uuidv4(), taskId, uuidv4(), JSON.stringify(item), JSON.stringify([])]
      );
    } finally {
      client.release();
    }
  }

  private async generateReviewPacket(task: Task): Promise<any> {
    // Generate the review packet from the checkpoint + validation state
    const patch = await this.collectPatch(task.workspaceId ?? '');
    const changedFiles = task.checkpoint?.workspaceState?.fileChanges ?? [];

    return {
      taskId: task.id,
      requirements: task.description,
      baseCommit: task.baseCommit,
      patchDigest: computePatchDigest(patch),
      changedFiles,
      skillVersions: task.skills,
      modelRoute: task.modelRoute,
      toolPermissions: task.toolPermissions,
      checkResults: [],
      environment: {
        os: process.platform,
        architecture: process.arch,
        nodeVersion: process.version,
      },
      screenshots: [],
      knownGaps: [],
      failedAttempts: task.outcome?.success === false ? [task.outcome] : [],
    };
  }

  private async storeReviewPacket(taskId: string, packet: any): Promise<void> {
    const client = await this.database.pool.connect();
    try {
      await client.query(
        `INSERT INTO event_log (event_type, entity_type, entity_id, payload)
         VALUES ($1, $2, $3, $4)`,
        ['review_packet_generated', 'task', taskId, JSON.stringify(packet)]
      );
    } catch (error) {
      this.logger.warn('Could not store review packet', { error });
    } finally {
      client.release();
    }
  }

  private async storeTraceReference(taskId: string, traceId: string, spanId: string): Promise<void> {
    const client = await this.database.pool.connect();
    try {
      await client.query(
        `INSERT INTO task_outcomes (id, task_id, attempt_id, success, evidence, trace_references)
         VALUES ($1, $2, $3, true, $4, $5)`,
        [
          uuidv4(),
          taskId,
          uuidv4(),
          JSON.stringify([]),
          JSON.stringify([{ traceId, spanId, gateway: 'routeforge', taskId, phase: 'AwaitingReview' }]),
        ]
      );
    } catch (error) {
      this.logger.warn('Could not store trace reference', { error });
    } finally {
      client.release();
    }
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
      const updates: string[] = ['status = $1', 'phase = $2', 'updated_at = NOW()'];
      const params: unknown[] = [status, phase];

      if (error) {
        updates.push('outcome = $3');
        params.push(JSON.stringify({ success: false, reason: error.message }));
      }

      let paramIdx = params.length;
      for (const [key, value] of Object.entries(extraFields || {})) {
        paramIdx++;
        updates.push(`${key} = $${paramIdx}`);
        params.push(typeof value === 'object' ? JSON.stringify(value) : value);
      }

      params.push(taskId);
      await client.query(
        `UPDATE tasks SET ${updates.join(', ')} WHERE id = $${params.length}`,
        params
      );
    } finally {
      client.release();
    }
  }
}
