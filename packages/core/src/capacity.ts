import { DevFoundryCore } from './core';
import {
  HardwareProfile,
  CapacityAdmission,
  Identity,
  Task,
} from './types';
import { DevFoundryError, CapacityError, ValidationError } from './errors';
import { createLogger } from './logging';

export interface CapacityConfig {
  cpuLimit: number;
  ramLimit: number;
  diskLimit: number;
  gpuLimit?: number;
  gpuMemoryLimit?: number;
  defaultProfile: string;
}

export interface AdmissionDecision {
  allowed: boolean;
  reason?: string;
  estimatedQueueTime?: number;
  recommendedProfile?: string;
}

export class CapacityAdmissionService {
  private logger = createLogger('capacity');
  private core: DevFoundryCore;
  private config: CapacityConfig;
  private queue: CapacityAdmission[] = [];
  private activeWorkloads: Map<string, CapacityAdmission> = new Map();

  constructor(core: DevFoundryCore, config: Partial<CapacityConfig> = {}) {
    this.core = core;
    this.config = {
      cpuLimit: 8,
      ramLimit: 16,
      diskLimit: 100,
      gpuLimit: 2,
      gpuMemoryLimit: 16,
      defaultProfile: 'default',
      ...config,
    };
  }

  async evaluate(task: Task, identity: Identity): Promise<AdmissionDecision> {
    this.logger.info('Evaluating capacity admission', {
      taskId: task.id,
      tenantId: task.tenantId,
    });

    const resourceEstimate = this.estimateResources(task);
    const queuePosition = this.getQueuePosition(resourceEstimate);
    const currentUsage = await this.getCurrentUsage();

    if (!this.hasSufficientResources(currentUsage, resourceEstimate)) {
      return {
        allowed: false,
        reason: 'Insufficient resources',
        estimatedQueueTime: queuePosition * 60,
        recommendedProfile: this.getSuggestedProfile(resourceEstimate),
      };
    }

    if (this.exceedsPriorityQuota(identity, resourceEstimate)) {
      return {
        allowed: false,
        reason: 'Priority quota exceeded',
        estimatedQueueTime: 0,
      };
    }

    return {
      allowed: true,
      estimatedQueueTime: queuePosition * 10,
    };
  }

  private estimateResources(task: Task): Required<CapacityAdmission> {
    const estimatedKVCache = this.estimateKVCache(task);

    return {
      taskId: task.id,
      cpuRequired: this.estimateCPU(task),
      ramRequired: this.estimateRAM(task),
      gpuRequired: this.estimateGPU(task),
      gpuMemoryRequired: this.estimateGPUMemory(task),
      estimatedKVCache,
      priority: this.estimatePriority(task),
      queueTime: 0,
    };
  }

  private estimateCPU(task: Task): number {
    return 2;
  }

  private estimateRAM(task: Task): number {
    return 4;
  }

  private estimateGPU(task: Task): number {
    const defaultModelRoutes = ['default', 'gpt-3.5', 'llama-2-7b'];
    if (defaultModelRoutes.includes(task.modelRoute)) {
      return 0;
    }
    return 1;
  }

  private estimateGPUMemory(task: Task): number {
    const defaultModelRoutes = ['default', 'gpt-3.5', 'llama-2-7b'];
    if (defaultModelRoutes.includes(task.modelRoute)) {
      return 0;
    }
    return 8;
  }

  private estimateKVCache(task: Task): number {
    const contextWindow = 4096;
    const layers = 32;
    const heads = 32;
    const headDim = 128;
    const batchSize = 1;
    
    return (layers * heads * headDim * contextWindow * batchSize) / 1024;
  }

  private estimatePriority(task: Task): number {
    return 10;
  }

  private getQueuePosition(estimate: Required<CapacityAdmission>): number {
    let position = 1;
    for (const workload of this.queue) {
      if (this.overlaps(workload, estimate)) {
        position++;
      }
    }
    return position;
  }

  private overlaps(a: CapacityAdmission, b: Required<CapacityAdmission>): boolean {
    return (
      (typeof a.cpuRequired === 'number' && typeof b.cpuRequired === 'number' && a.cpuRequired + b.cpuRequired > this.config.cpuLimit) ||
      (typeof a.ramRequired === 'number' && typeof b.ramRequired === 'number' && a.ramRequired + b.ramRequired > this.config.ramLimit) ||
      (typeof a.gpuRequired === 'number' && typeof b.gpuRequired === 'number' && a.gpuRequired + b.gpuRequired > (this.config.gpuLimit || 0)) ||
      (typeof a.gpuMemoryRequired === 'number' && typeof b.gpuMemoryRequired === 'number' && a.gpuMemoryRequired + b.gpuMemoryRequired > (this.config.gpuMemoryLimit || 0))
    );
  }

  private async getCurrentUsage(): Promise<Map<string, number>> {
    const usage = new Map<string, number>();

    usage.set('cpu', 0);
    usage.set('ram', 0);
    usage.set('gpu', 0);
    usage.set('gpuMemory', 0);

    return usage;
  }

  private hasSufficientResources(
    currentUsage: Map<string, number>,
    estimate: Required<CapacityAdmission>
  ): boolean {
    return (
      (currentUsage.get('cpu') || 0) + estimate.cpuRequired <= this.config.cpuLimit &&
      (currentUsage.get('ram') || 0) + estimate.ramRequired <= this.config.ramLimit &&
      (!estimate.gpuRequired ||
        (currentUsage.get('gpu') || 0) + estimate.gpuRequired <= (this.config.gpuLimit || 0)) &&
      (!estimate.gpuMemoryRequired ||
        (currentUsage.get('gpuMemory') || 0) + estimate.gpuMemoryRequired <= (this.config.gpuMemoryLimit || 0))
    );
  }

  private exceedsPriorityQuota(identity: Identity, estimate: Required<CapacityAdmission>): boolean {
    return false;
  }

  private getSuggestedProfile(estimate: Required<CapacityAdmission>): string {
    if (estimate.gpuRequired && estimate.gpuRequired > 0) {
      return 'gpu-medium';
    }
    if (estimate.ramRequired > 8) {
      return 'ram-large';
    }
    return 'default';
  }

  async recordWorkload(task: Task, estimate: Required<CapacityAdmission>): Promise<void> {
    this.activeWorkloads.set(task.id, estimate);
  }

  async completeWorkload(taskId: string): Promise<void> {
    this.activeWorkloads.delete(taskId);
  }

  async addToQueue(task: Task, estimate: Required<CapacityAdmission>): Promise<void> {
    this.queue.push(estimate);
  }

  async removeFromQueue(taskId: string): Promise<void> {
    this.queue = this.queue.filter((item) => item.taskId !== taskId);
  }

  getActiveWorkloads(): Map<string, CapacityAdmission> {
    return this.activeWorkloads;
  }

  getQueue(): CapacityAdmission[] {
    return this.queue;
  }

  getStats(): { active: number; queued: number; cpuUsed: number; ramUsed: number } {
    let cpuUsed = 0;
    let ramUsed = 0;

    this.activeWorkloads.forEach((w) => {
      cpuUsed += w.cpuRequired;
      ramUsed += w.ramRequired;
    });

    return {
      active: this.activeWorkloads.size,
      queued: this.queue.length,
      cpuUsed,
      ramUsed,
    };
  }
}
