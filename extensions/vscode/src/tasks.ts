import * as vscode from 'vscode';

import { DevFoundryClient, DevFoundryTask } from './client';

const CACHE_MS = 15_000;
const STATUS_ICONS: Record<string, vscode.ThemeIcon> = {
  Pending: new vscode.ThemeIcon('clock'),
  Running: new vscode.ThemeIcon('sync'),
  Validating: new vscode.ThemeIcon('checklist'),
  AwaitingReview: new vscode.ThemeIcon('eye'),
  Completed: new vscode.ThemeIcon('pass'),
  Failed: new vscode.ThemeIcon('error'),
  Cancelled: new vscode.ThemeIcon('circle-slash'),
};

class TaskNode extends vscode.TreeItem {}

export class TasksProvider implements vscode.TreeDataProvider<TaskNode> {
  private _onDidChangeTreeData = new vscode.EventEmitter<TaskNode | undefined>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private cache: DevFoundryTask[] | undefined;
  private cacheAt = 0;
  private inflight: Promise<DevFoundryTask[]> | undefined;

  constructor(private readonly client: DevFoundryClient) {}

  refresh(): void {
    this.cache = undefined;
    this.cacheAt = 0;
    this._onDidChangeTreeData.fire(undefined);
  }

  getTreeItem(element: TaskNode): vscode.TreeItem {
    return element;
  }

  async getChildren(): Promise<TaskNode[]> {
    const tasks = await this.load();
    return tasks.map((t) => {
      const item = new TaskNode(t.description ? t.description.slice(0, 60) : t.id);
      item.description = `${t.status} / ${t.phase}`;
      item.contextValue = t.status;
      item.iconPath = STATUS_ICONS[t.status] ?? new vscode.ThemeIcon('circle-outline');
      item.tooltip = new vscode.MarkdownString(
        [`**Task** \`${t.id}\``, t.description, `**Status**: ${t.status} (${t.phase})`].join('\n\n')
      );
      item.command = {
        command: 'devfoundry.reviewDiff',
        title: 'Review Task Diff',
        arguments: [t.id],
      };
      return item;
    });
  }

  private async load(): Promise<DevFoundryTask[]> {
    const now = Date.now();
    if (this.cache && now - this.cacheAt < CACHE_MS) {
      return this.cache;
    }
    if (!this.inflight) {
      this.inflight = this.client
        .getTasks()
        .then((tasks) => {
          this.cache = tasks;
          this.cacheAt = Date.now();
          this.inflight = undefined;
          return tasks;
        })
        .catch((err) => {
          this.inflight = undefined;
          vscode.window.setStatusBarMessage(
            `DevFoundry: ${err instanceof Error ? err.message : 'unavailable'}`,
            5000
          );
          return this.cache ?? [];
        });
    }
    return this.inflight;
  }
}
