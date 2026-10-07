import { spawn } from 'child_process';
import { createLogger } from './logging';
import { BuildResult, LintResult, LintError, LintWarning, TestResult, SecurityResult, SecurityFinding, UIResult, ValidationPipelineResult } from './types';

export interface ValidationOptions {
  workspacePath: string;
  buildCommand?: string;
  lintCommand?: string;
  testCommand?: string;
  securityCommand?: string;
  uiTestCommand?: string;
  timeout?: number;
}

export class ValidationPipeline {
  private logger = createLogger('validation');
  private options: ValidationOptions;

  constructor(options: ValidationOptions) {
    this.options = {
      buildCommand: 'npm run build',
      lintCommand: 'npm run lint',
      testCommand: 'npm test',
      securityCommand: 'npx npm-audit-ci',
      uiTestCommand: 'npm run test:ui',
      timeout: 300000,
      ...options,
    };
  }

  async runAll(): Promise<ValidationPipelineResult> {
    this.logger.info('Starting validation pipeline', { workspace: this.options.workspacePath });

    const results: ValidationPipelineResult = {
      build: await this.runBuild(),
      lint: await this.runLint(),
      tests: await this.runTests(),
      security: await this.runSecurity(),
      ui: await this.runUITests(),
    };

    const overallSuccess =
      results.build.success &&
      results.lint.success &&
      results.tests.every((t) => t.status !== 'failed') &&
      results.security.success;

    this.logger.info('Validation pipeline complete', {
      workspace: this.options.workspacePath || 'unknown',
    }, {
      overallSuccess,
    });

    return results;
  }

  private async runBuild(): Promise<BuildResult> {
    this.logger.info('Running build verification', {
      command: this.options.buildCommand || 'npm run build',
    });

    const startTime = Date.now();
    let success = false;
    let output = '';

    try {
      const command = this.options.buildCommand || 'npm run build';
      const result = await this.runCommand(command, this.options.workspacePath);
      success = result.code === 0;
      output = result.stdout || '';
    } catch (error) {
      this.logger.error('Build failed', { error: (error as Error).message });
    }

    return {
      success,
      output,
      duration: Date.now() - startTime,
    };
  }

  private async runLint(): Promise<LintResult> {
    this.logger.info('Running lint verification', {
      command: this.options.lintCommand || 'npm run lint',
    });

    const startTime = Date.now();
    let success = false;
    const errors: LintError[] = [];
    const warnings: LintWarning[] = [];

    try {
      const command = this.options.lintCommand || 'npm run lint';
      const result = await this.runCommand(command, this.options.workspacePath);
      success = result.code === 0;
      this.parseLintOutput(result.stdout || '', errors, warnings);
    } catch (error) {
      this.logger.error('Lint failed', { error: (error as Error).message });
    }

    return {
      success,
      errors,
      warnings,
      duration: Date.now() - startTime,
    };
  }

  private async runTests(): Promise<TestResult[]> {
    this.logger.info('Running tests', {
      command: this.options.testCommand || 'npm test',
    });

    const startTime = Date.now();
    const results: TestResult[] = [];

    try {
      const command = this.options.testCommand || 'npm test';
      const result = await this.runCommand(command, this.options.workspacePath);
      
      if (result.code === 0) {
        const testResults = this.parseTestOutput(result.stdout || '');
        results.push(...testResults);
      } else {
        results.push({
          name: 'test suite',
          path: 'all',
          status: 'failed',
          duration: Date.now() - startTime,
          output: result.stderr || '',
        });
      }
    } catch (error) {
      this.logger.error('Tests failed', { error: (error as Error).message });
      results.push({
        name: 'test suite',
        path: 'all',
        status: 'failed',
        duration: Date.now() - startTime,
      });
    }

    return results;
  }

  private async runSecurity(): Promise<SecurityResult> {
    this.logger.info('Running security scan', {
      command: this.options.securityCommand || 'npx npm-audit-ci',
    });

    const startTime = Date.now();
    let success = true;
    const findings: SecurityFinding[] = [];

    try {
      const command = this.options.securityCommand || 'npx npm-audit-ci';
      const result = await this.runCommand(command, this.options.workspacePath);
      success = result.code === 0;
      
      if (!success) {
        findings.push({
          severity: 'high',
          type: 'security_vulnerability',
          file: 'package.json',
          line: 1,
          column: 1,
          message: 'Security vulnerabilities found',
          recommendation: 'Run npm audit fix to resolve',
        });
      }
    } catch (error) {
      this.logger.error('Security scan failed', { error: (error as Error).message });
    }

    return {
      success,
      scanner: 'npm-audit-ci',
      findings,
      duration: Date.now() - startTime,
    };
  }

  private async runUITests(): Promise<UIResult[]> {
    this.logger.info('Running UI tests', {
      command: this.options.uiTestCommand || 'npm run test:ui',
    });

    const startTime = Date.now();
    const results: UIResult[] = [];

    try {
      const command = this.options.uiTestCommand || 'npm run test:ui';
      const result = await this.runCommand(command, this.options.workspacePath);
      
      if (result.code === 0) {
        results.push({
          test: 'ui-snapshot',
          status: 'passed',
          duration: Date.now() - startTime,
        });
      } else {
        results.push({
          test: 'ui-snapshot',
          status: 'failed',
          duration: Date.now() - startTime,
        });
      }
    } catch (error) {
      this.logger.error('UI tests failed', { error: (error as Error).message });
    }

    return results;
  }

  private async runCommand(command: string, cwd: string): Promise<{ code: number; stdout: string; stderr: string }> {
    return new Promise((resolve) => {
      const [cmd, ...args] = command.split(' ');
      const proc = spawn(cmd, args, {
        cwd,
        shell: true,
        timeout: this.options.timeout,
      });

      let stdout = '';
      let stderr = '';

      proc.stdout.on('data', (data) => {
        stdout += data.toString();
      });

      proc.stderr.on('data', (data) => {
        stderr += data.toString();
      });

      proc.on('close', (code) => {
        resolve({
          code: code || 0,
          stdout,
          stderr,
        });
      });

      proc.on('error', (error) => {
        resolve({
          code: 1,
          stdout,
          stderr: error.message,
        });
      });
    });
  }

  private parseLintOutput(output: string, errors: LintError[], warnings: LintWarning[]): void {
    const errorLines = output.split('\n').filter((line) => line.includes('error'));
    const warningLines = output.split('\n').filter((line) => line.includes('warning'));

    errorLines.forEach((line) => {
      errors.push({
        file: this.extractFile(line),
        line: this.extractLine(line),
        column: 1,
        message: line.trim(),
        rule: 'custom',
      });
    });

    warningLines.forEach((line) => {
      warnings.push({
        file: this.extractFile(line),
        line: this.extractLine(line),
        column: 1,
        message: line.trim(),
        rule: 'custom',
      });
    });
  }

  private parseTestOutput(output: string): TestResult[] {
    const results: TestResult[] = [];
    const lines = output.split('\n');

    lines.forEach((line) => {
      if (line.includes('PASS') || line.includes('FAIL')) {
        const parts = line.split(' ');
        results.push({
          name: parts[1] || 'unknown',
          path: parts[0] || 'unknown',
          status: line.includes('PASS') ? 'passed' : 'failed',
          duration: 0,
        });
      }
    });

    return results;
  }

  private extractFile(line: string): string {
    const match = line.match(/([^:]+\.ts)/);
    return match ? match[1] : 'unknown';
  }

  private extractLine(line: string): number {
    const match = line.match(/:(\d+):/);
    return match ? parseInt(match[1], 10) : 1;
  }
}
