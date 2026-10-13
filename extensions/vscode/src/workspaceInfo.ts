import * as vscode from 'vscode';

import { DevFoundryClient } from './client';

export class WorkspaceInfoProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
  private _onDidChangeTreeData = new vscode.EventEmitter<vscode.TreeItem | undefined>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  constructor(
    private readonly client: DevFoundryClient,
    private readonly context: vscode.ExtensionContext
  ) {}

  refresh(): void {
    this._onDidChangeTreeData.fire(undefined);
  }

  getTreeItem(element: vscode.TreeItem): vscode.TreeItem {
    return element;
  }

  async getChildren(): Promise<vscode.TreeItem[]> {
    const config = vscode.workspace.getConfiguration('devfoundry');
    const baseUrl = config.get<string>('url') ?? 'http://localhost:3000';
    const projectId = config.get<string>('projectId') || '(not set)';
    const userId = config.get<string>('userId') || '(not set)';

    const token = await this.context.secrets.get('devfoundry.token');
    const loggedIn = token !== undefined;

    let taskCount = '?';
    try {
      taskCount = String((await this.client.getTasks()).length);
    } catch {
      taskCount = '?';
    }

    const items: vscode.TreeItem[] = [];

    const connection = new vscode.TreeItem('Connection', vscode.TreeItemCollapsibleState.None);
    connection.description = loggedIn ? 'Signed in' : 'Not signed in';
    connection.iconPath = new vscode.ThemeIcon(loggedIn ? 'pass' : 'sign-out');
    connection.contextValue = 'connection';
    items.push(connection);

    const url = new vscode.TreeItem('API URL', vscode.TreeItemCollapsibleState.None);
    url.description = baseUrl;
    url.iconPath = new vscode.ThemeIcon('server');
    url.contextValue = 'url';
    items.push(url);

    const project = new vscode.TreeItem('Project ID', vscode.TreeItemCollapsibleState.None);
    project.description = projectId;
    project.iconPath = new vscode.ThemeIcon('project');
    project.contextValue = 'projectId';
    items.push(project);

    const user = new vscode.TreeItem('User ID', vscode.TreeItemCollapsibleState.None);
    user.description = userId;
    user.iconPath = new vscode.ThemeIcon('person');
    user.contextValue = 'userId';
    items.push(user);

    const tasks = new vscode.TreeItem('Tasks (latest page)', vscode.TreeItemCollapsibleState.None);
    tasks.description = `${taskCount} task(s)`;
    tasks.iconPath = new vscode.ThemeIcon('checklist');
    tasks.contextValue = 'taskCount';
    items.push(tasks);

    const runTask = new vscode.TreeItem('Delegate a Task…', vscode.TreeItemCollapsibleState.None);
    runTask.command = { command: 'devfoundry.runTask', title: 'Delegate a Task' };
    runTask.iconPath = new vscode.ThemeIcon('play');
    items.push(runTask);

    const connect = new vscode.TreeItem('Connect to DevFoundry…', vscode.TreeItemCollapsibleState.None);
    connect.command = { command: 'devfoundry.connect', title: 'Connect to DevFoundry' };
    connect.iconPath = new vscode.ThemeIcon('plug');
    items.push(connect);

    return items;
  }
}
