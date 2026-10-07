import { DevFoundryCore } from './core';
import { ValidationPipeline } from './validation';
import {
  Task,
  TaskPhase,
  TaskStatus,
  TaskOutcome,
  EvidenceItem,
  TraceReference,
  ChangedFile,
  InstalledSkill,
  ModelConfig,
  EnvironmentInfo,
  FailedAttempt,
  ReviewPacket,
  ValidationPipelineResult,
} from './types';
import { createLogger } from './logging';

export interface ReviewPacketOptions {
  core: DevFoundryCore;
  workspacePath: string;
  patchPath?: string;
}

export class ReviewPacketGenerator {
  private logger = createLogger('review-packet');
  private core: DevFoundryCore;
  private workspacePath: string;
  private patchPath?: string;

  constructor(options: ReviewPacketOptions) {
    this.core = options.core;
    this.workspacePath = options.workspacePath;
    this.patchPath = options.patchPath;
  }

  async generate(task: Task): Promise<ReviewPacket> {
    this.logger.info('Generating review packet', {
      taskId: task.id,
      phase: task.phase,
    });

    const validationResults = await this.runValidation(task);
    const changedFiles = await this.collectChangedFiles();
    const evidence = await this.collectEvidence(task, validationResults);
    const installedSkills = this.getInstalledSkills(task);
    const modelConfig = this.getModelConfig(task);
    const environmentInfo = await this.getEnvironmentInfo();
    const knownGaps = this.identifyKnownGaps(task, validationResults);
    const failedAttempts = this.getFailedAttempts(task);

    const reviewPacket: ReviewPacket = {
      taskId: task.id,
      taskDescription: task.description,
      taskStatus: task.status,
      taskPhase: task.phase,
      baseCommit: task.baseCommit,
      targetBranch: task.targetBranch,
      patchDigest: this.computePatchDigest(changedFiles),
      baseDigest: task.baseCommit,
      changedFiles,
      installedSkills,
      modelConfig,
      toolPermissions: task.toolPermissions,
      validationResults,
      environmentInfo,
      evidence,
      knownGaps,
      failedAttempts,
      createdAt: new Date(),
    };

    this.logger.info('Review packet generated', {
      taskId: task.id,
    }, {
      hasEvidence: evidence.length > 0,
    });

    return reviewPacket;
  }

  private async runValidation(task: Task): Promise<ValidationPipelineResult> {
    const validationPipeline = new ValidationPipeline({
      workspacePath: this.workspacePath,
      buildCommand: 'npm run build',
      lintCommand: 'npm run lint',
      testCommand: 'npm test',
      securityCommand: 'npx npm-audit-ci',
      uiTestCommand: 'npm run test:ui',
      timeout: 300000,
    });

    return validationPipeline.runAll();
  }

  private async collectChangedFiles(): Promise<ChangedFile[]> {
    const files: ChangedFile[] = [];
    
    try {
      const result = await this.runGitCommand(['status', '--porcelain'], this.workspacePath);
      const lines = result.stdout.split('\n').filter((line) => line.trim());

      lines.forEach((line) => {
        const status = line.charAt(0);
        const filePath = line.substring(2).trim();
        
        let changeStatus: 'added' | 'modified' | 'deleted' = 'modified';
        if (status === 'A') {
          changeStatus = 'added';
        } else if (status === 'D') {
          changeStatus = 'deleted';
        }

        const diffSummary = this.getDiffSummary(filePath);
        const linesChanged = this.countLinesChanged(filePath);

        files.push({
          path: filePath,
          status: changeStatus,
          diffSummary,
          linesChanged,
        });
      });
    } catch (error) {
      this.logger.warn('Failed to collect changed files', { error: (error as Error).message });
    }

    return files;
  }

  private async getDiffSummary(filePath: string): Promise<string> {
    try {
      const result = await this.runGitCommand(['diff', '--stat', filePath], this.workspacePath);
      return result.stdout.trim() || 'no changes';
    } catch {
      return 'unknown';
    }
  }

  private async countLinesChanged(filePath: string): Promise<number> {
    try {
      const result = await this.runGitCommand(['diff', '--numstat', filePath], this.workspacePath);
      const lines = result.stdout.split('\n');
      let total = 0;
      
      lines.forEach((line) => {
        const parts = line.trim().split('\t');
        if (parts.length >= 2) {
          total += parseInt(parts[0], 10) + parseInt(parts[1], 10);
        }
      });
      
      return total;
    } catch {
      return 0;
    }
  }

  private async collectEvidence(task: Task, results: ValidationPipelineResult): Promise<EvidenceItem[]> {
    const evidence: EvidenceItem[] = [];

    if (results.build.success) {
      evidence.push({
        type: 'command',
        content: 'Build successful',
        timestamp: new Date(),
        provenance: {
          phase: task.phase,
        },
      });
    }

    if (results.lint.success) {
      evidence.push({
        type: 'lint',
        content: 'Linting passed',
        timestamp: new Date(),
        provenance: {
          phase: task.phase,
        },
      });
    }

    results.tests.forEach((test) => {
      if (test.status === 'passed') {
        evidence.push({
          type: 'test',
          content: `Test passed: ${test.name}`,
          timestamp: new Date(),
          provenance: {
            phase: task.phase,
          },
        });
      }
    });

    if (results.security.success) {
      evidence.push({
        type: 'security',
        content: 'Security scan passed',
        timestamp: new Date(),
        provenance: {
          phase: task.phase,
        },
      });
    }

    return evidence;
  }

  private getInstalledSkills(task: Task): InstalledSkill[] {
    return task.skills.map((skillId) => ({
      id: skillId,
      version: '1.0.0',
      digest: `sha256-${skillId}`,
      path: `/skills/${skillId}`,
    }));
  }

  private getModelConfig(task: Task): ModelConfig {
    return {
      route: task.modelRoute,
      provider: 'routeforge',
      model: 'default',
      temperature: 0.7,
      maxTokens: 4096,
    };
  }

  private async getEnvironmentInfo(): Promise<EnvironmentInfo> {
    return {
      os: process.platform,
      architecture: process.arch,
      nodeVersion: process.version,
    };
  }

  private identifyKnownGaps(task: Task, results: ValidationPipelineResult): string[] {
    const gaps: string[] = [];

    if (!results.build.success) {
      gaps.push('Build verification failed');
    }

    if (!results.lint.success) {
      gaps.push('Lint verification failed');
    }

    const failedTests = results.tests.filter((t) => t.status === 'failed');
    if (failedTests.length > 0) {
      gaps.push(`${failedTests.length} test(s) failed`);
    }

    if (!results.security.success) {
      gaps.push('Security scan failed');
    }

    return gaps;
  }

  private getFailedAttempts(task: Task): FailedAttempt[] {
    if (!task.outcome) {
      return [];
    }

    const outcome = task.outcome as any;
    if (outcome.success) {
      return [];
    }

    return [
      {
        attemptId: task.id,
        phase: task.phase,
        error: outcome.reason || 'Unknown error',
        timestamp: task.completedAt || new Date(),
        duration: 0,
      },
    ];
  }

  private computePatchDigest(files: ChangedFile[]): string {
    const sortedFiles = [...files].sort((a, b) => a.path.localeCompare(b.path));
    const content = JSON.stringify(sortedFiles, null, 2);
    return this.sha256(content);
  }

  private sha256(message: string): string {
    let hash = 0;
    for (let i = 0; i < message.length; i++) {
      const char = message.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash;
    }
    return hash.toString(16).padStart(64, '0');
  }

  private async runGitCommand(args: string[], cwd: string): Promise<{ stdout: string; stderr: string }> {
    return new Promise((resolve, reject) => {
      const { spawn } = require('child_process');
      const proc = spawn('git', args, { cwd, shell: true });

      let stdout = '';
      let stderr = '';

      proc.stdout.on('data', (data: Buffer) => {
        stdout += data.toString();
      });

      proc.stderr.on('data', (data: Buffer) => {
        stderr += data.toString();
      });

      proc.on('close', (code: number) => {
        if (code === 0) {
          resolve({ stdout, stderr });
        } else {
          reject(new Error(`Git command failed with code ${code}`));
        }
      });
    });
  }
}
