import * as vscode from 'vscode';

import { DevFoundryClient } from './client';
import { registerCommands } from './commands';
import { TasksProvider } from './tasks';
import { WorkspaceInfoProvider } from './workspaceInfo';

export function activate(context: vscode.ExtensionContext): void {
  const tokenGetter = async (): Promise<string | undefined> =>
    (await context.secrets.get('devfoundry.token')) ?? undefined;
  const tokenSetter = async (token: string | undefined): Promise<void> => {
    if (token === undefined) {
      await context.secrets.delete('devfoundry.token');
    } else {
      await context.secrets.store('devfoundry.token', token);
    }
  };

  const client = new DevFoundryClient(
    () => vscode.workspace.getConfiguration('devfoundry').get<string>('url') ?? 'http://localhost:3000',
    tokenGetter,
    tokenSetter
  );

  const tasksProvider = new TasksProvider(client);
  const workspaceInfoProvider = new WorkspaceInfoProvider(client, context);

  context.subscriptions.push(
    vscode.window.registerTreeDataProvider('devfoundry.tasks', tasksProvider),
    vscode.window.registerTreeDataProvider('devfoundry.workspace', workspaceInfoProvider),
    ...registerCommands(context, client, tasksProvider, workspaceInfoProvider)
  );
}

export function deactivate(): void {
  // No long-running resources are held by the thin client.
}
