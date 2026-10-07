import { Task, TaskPhase, TaskOutcome, EvidenceItem, TraceReference } from '@dev-foundry/core';
import { Pool, Client } from 'pg';
import { v4 as uuidv4 } from 'uuid';
import { createLogger } from '@dev-foundry/core';
import * as path from 'path';
import * as fs from 'fs/promises';

export interface OutcomeLedgerConfig {
  databaseUrl: string;
  langfuseUrl?: string;
}

export interface AttemptRecord {
  attemptId: string;
  taskId: string;
  phase: TaskPhase;
  timestamp: Date;
  success: boolean;
  duration: number;
  error?: string;
  checkpointId?: string;
}

export interface EvidenceStorage {
  storagePath: string;
  storageType: 'local' | 's3';
  retentionDays: number;
}

export class OutcomeLedger {
  private pool: Pool;
  private langfuseUrl?: string;
  private logger = createLogger('outcome-ledger');
  private evidenceStorage: EvidenceStorage;

  constructor(config: OutcomeLedgerConfig) {
    const match = config.databaseUrl.match(/postgres:\/\/([^:]+):([^@]+)@([^:]+):(\d+)\/(.+)/);
    if (!match) {
      throw new Error('Invalid DATABASE_URL');
    }

    const [, username, password, host, port, database] = match;
    this.pool = new Pool({
      host,
      port: parseInt(port, 10),
      database,
      user: username,
      password,
    });

    this.langfuseUrl = config.langfuseUrl;
    this.evidenceStorage = {
      storagePath: process.env.EVIDENCE_STORAGE_PATH || '/var/data/evidence',
      storageType: 'local' as const,
      retentionDays: parseInt(process.env.EVIDENCE_RETENTION_DAYS || '30', 10),
    };
  }

  async connect(): Promise<void> {
    await this.pool.connect();
    this.logger.info('Connected to outcome ledger database');
  }

  async disconnect(): Promise<void> {
    await this.pool.end();
    this.logger.info('Disconnected from outcome ledger database');
  }

  /**
   * Record a task attempt
   */
  async recordAttempt(
    taskId: string,
    phase: TaskPhase,
    success: boolean,
    error?: string,
    checkpointId?: string
  ): Promise<AttemptRecord> {
    const attemptId = uuidv4();
    const startTime = new Date();
    const endTime = new Date();
    const duration = endTime.getTime() - startTime.getTime();

    const record: AttemptRecord = {
      attemptId,
      taskId,
      phase,
      timestamp: startTime,
      success,
      duration,
      error,
      checkpointId,
    };

    await this.pool.query(
      `
      INSERT INTO task_outcomes (
        id, task_id, attempt_id, success, reason, evidence, trace_references, created_at
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
      `,
      [
        uuidv4(),
        taskId,
        attemptId,
        success,
        error || null,
        JSON.stringify([]),
        JSON.stringify([]),
        startTime,
      ]
    );

    this.logger.info('Recorded task attempt', { 
      attemptId, 
      taskId, 
      phase, 
      success: String(success) 
    });
    
    return record;
  }

  /**
   * Record task outcome with evidence
   */
  async recordOutcome(
    taskId: string,
    attemptId: string,
    success: boolean,
    reason?: string,
    evidence: EvidenceItem[] = [],
    traceReferences: TraceReference[] = []
  ): Promise<void> {
    const outcomeId = uuidv4();

    // Store evidence in local storage
    for (const item of evidence) {
      await this.storeEvidenceItem(outcomeId, item);
    }

    // Save to database
    await this.pool.query(
      `
      UPDATE task_outcomes 
      SET reason = $1, 
          evidence = $2, 
          trace_references = $3,
          updated_at = NOW()
      WHERE task_id = $4 AND attempt_id = $5
      `,
      [
        reason || null,
        JSON.stringify(evidence),
        JSON.stringify(traceReferences),
        taskId,
        attemptId,
      ]
    );

    // Update task outcome in tasks table
    await this.pool.query(
      `
      UPDATE tasks 
      SET outcome = $1, 
          status = $2, 
          phase = $3,
          completed_at = NOW(),
          updated_at = NOW()
      WHERE id = $4
      `,
      [
        JSON.stringify({ success, reason, evidence, traceReferences }),
        success ? 'Completed' : 'Failed',
        success ? 'Completed' : 'Failed',
        taskId,
      ]
    );

    this.logger.info('Recorded task outcome', { 
      taskId, 
      attemptId, 
      success: String(success) 
    });
  }

  /**
   * Store evidence item in local filesystem
   */
  private async storeEvidenceItem(outcomeId: string, item: EvidenceItem): Promise<string> {
    const filePath = `${this.evidenceStorage.storagePath}/${outcomeId}/${item.type}-${uuidv4()}.json`;
    
    // Create directory if it doesn't exist
    const dir = path.dirname(filePath);
    await fs.mkdir(dir, { recursive: true });
    
    const content = JSON.stringify(item, null, 2);
    await fs.writeFile(filePath, content, 'utf8');

    this.logger.info('Stored evidence item', { 
      outcomeId, 
      type: item.type, 
      path: filePath 
    });

    return filePath;
  }

  /**
   * Link Langfuse trace to task
   */
  async linkLangfuseTrace(
    taskId: string,
    attemptId: string,
    traceId: string,
    spanId?: string,
    phase?: TaskPhase
  ): Promise<void> {
    await this.pool.query(
      `
      INSERT INTO task_outcomes (trace_references)
      SELECT jsonb_set(trace_references, '{0}', $1::jsonb, true)
      FROM task_outcomes
      WHERE task_id = $2 AND attempt_id = $3
      `,
      [
        JSON.stringify({
          traceId,
          spanId,
          gateway: 'routeforge',
          phase: phase || 'Running',
        }),
        taskId,
        attemptId,
      ]
    );

    this.logger.info('Linked Langfuse trace', { taskId, attemptId, traceId });
  }

  /**
   * Get task outcome with evidence
   */
  async getTaskOutcome(taskId: string, attemptId?: string): Promise<TaskOutcome | null> {
    const result = await this.pool.query(
      `
      SELECT * FROM task_outcomes 
      WHERE task_id = $1
      ${attemptId ? 'AND attempt_id = $2' : ''}
      ORDER BY created_at DESC
      LIMIT 1
      `,
      attemptId ? [taskId, attemptId] : [taskId]
    );

    if (result.rows.length === 0) {
      return null;
    }

    const row = result.rows[0];
    
    return {
      success: row.success,
      reason: row.reason,
      evidence: row.evidence || [],
      traceReferences: row.trace_references || [],
    };
  }

  /**
   * Get analytics data for tasks
   */
  async getTaskAnalytics(
    tenantId?: string,
    projectId?: string,
    startDate?: Date,
    endDate?: Date
  ): Promise<Record<string, unknown>[]> {
    let query = `
      SELECT 
        t.project_id,
        t.phase,
        t.status,
        COUNT(*) as task_count,
        AVG(EXTRACT(EPOCH FROM (t.completed_at - t.started_at))) as avg_duration,
        SUM(CASE WHEN t.status = 'Completed' THEN 1 ELSE 0 END) as completed_count,
        SUM(CASE WHEN t.status IN ('Failed', 'Cancelled') THEN 1 ELSE 0 END) as failed_count
      FROM tasks t
      WHERE 1=1
    `;
    const params: any[] = [];
    const conditions: string[] = [];

    if (tenantId) {
      conditions.push('t.tenant_id = $' + (params.length + 1));
      params.push(tenantId);
    }

    if (projectId) {
      conditions.push('t.project_id = $' + (params.length + 1));
      params.push(projectId);
    }

    if (startDate) {
      conditions.push('t.created_at >= $' + (params.length + 1));
      params.push(startDate);
    }

    if (endDate) {
      conditions.push('t.created_at <= $' + (params.length + 1));
      params.push(endDate);
    }

    if (conditions.length > 0) {
      query += ' AND ' + conditions.join(' AND ');
    }

    query += ' GROUP BY t.project_id, t.phase, t.status ORDER BY t.project_id, t.phase, t.status';

    const result = await this.pool.query(query, params);
    return result.rows;
  }

  /**
   * Get task quality metrics
   */
  async getQualityMetrics(
    projectId?: string,
    days: number = 30
  ): Promise<Record<string, unknown>> {
    const result = await this.pool.query(
      `
      SELECT 
        COUNT(*) as total_tasks,
        AVG(retry_count) as avg_retries,
        SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) as completed_count,
        SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) as failed_count,
        SUM(CASE WHEN status = 'Cancelled' THEN 1 ELSE 0 END) as cancelled_count,
        AVG(EXTRACT(EPOCH FROM (completed_at - created_at))) as avg_completion_time,
        SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as success_rate
      FROM tasks
      WHERE created_at >= NOW() - INTERVAL '${days} days'
        ${projectId ? 'AND project_id = $1' : ''}
      `,
      projectId ? [projectId] : []
    );

    return result.rows[0];
  }

  /**
   * Get evidence storage stats
   */
  async getEvidenceStats(): Promise<Record<string, unknown>> {
    let totalSize = 0;
    let totalFiles = 0;

    try {
      const files = await fs.readdir(this.evidenceStorage.storagePath, { recursive: true });
      for (const file of files) {
        const stats = await fs.stat(path.join(this.evidenceStorage.storagePath, file));
        totalSize += stats.size;
        totalFiles++;
      }
    } catch (error) {
      this.logger.warn('Could not read evidence storage', { error });
    }

    return {
      totalSize: totalSize,
      totalFiles: totalFiles,
      retentionDays: this.evidenceStorage.retentionDays,
    };
  }

  /**
   * Cleanup old evidence and outcomes
   */
  async cleanupOldData(): Promise<void> {
    const cutoffDate = new Date();
    cutoffDate.setDate(cutoffDate.getDate() - this.evidenceStorage.retentionDays);

    // Delete old outcomes
    await this.pool.query(
      `
      DELETE FROM task_outcomes
      WHERE created_at < $1
      `,
      [cutoffDate]
    );

    // Delete old evidence files
    try {
      const files = await fs.readdir(this.evidenceStorage.storagePath, { recursive: true });
      for (const file of files) {
        const filePath = path.join(this.evidenceStorage.storagePath, file);
        const stats = await fs.stat(filePath);
        if (stats.mtime < cutoffDate) {
          await fs.unlink(filePath);
        }
      }
    } catch (error) {
      this.logger.warn('Could not cleanup old evidence files', { error });
    }

    this.logger.info('Cleaned up old data', { 
      cutoffDate: cutoffDate.toISOString(),
    });
  }
}
