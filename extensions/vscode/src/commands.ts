import * as vscode from 'vscode';

import { DevFoundryApiError, DevFoundryClient, DevFoundryTask } from './client';

const TASK_CACHE_MS = 15_000;
const PREVIEW_CHARS = 200;

interface TaskQuickPickItem extends vscode.QuickPickItem {
  task: DevFoundryTask;
}

function truncate(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, max)}…`;
}

async function withStatus<T>(label: string, work: () => Thenable<T>): Promise<T> {
  return vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: label },
    work
  );
}

function apiErrorMessage(err: unknown): string {
  if (err instanceof DevFoundryApiError) {
    return err.message;
  }
  return err instanceof Error ? err.message : String(err);
}

function toTaskItems(tasks: DevFoundryTask[], filterOpen = false): TaskQuickPickItem[] {
  const filtered = filterOpen
    ? tasks.filter((t) => !['Completed', 'Failed', 'Cancelled'].includes(t.status))
    : tasks;
  return filtered.map((t) => ({
    label: truncate(t.description || t.id, 60),
    description: `${t.status} / ${t.phase}`,
    detail: t.id,
    task: t,
  }));
}

async function pickTask(
  client: DevFoundryClient,
  title: string,
  filterOpen = false
): Promise<DevFoundryTask | undefined> {
  const tasks = await withStatus('Loading tasks…', () => client.getTasks());
  const items = toTaskItems(tasks, filterOpen);
  if (items.length === 0) {
    vscode.window.showInformationMessage(
      filterOpen ? 'No open DevFoundry tasks.' : 'No DevFoundry tasks found.'
    );
    return undefined;
  }
  const picked = await vscode.window.showQuickPick(items, { title, placeHolder: 'Select a task' });
  return picked?.task;
}

/** Project/user IDs are required by POST /api/tasks; get them from config or prompt once. */
async function resolveTaskOwner(): Promise<{ projectId: string; userId: string } | undefined> {
  const config = vscode.workspace.getConfiguration('devfoundry');
  let projectId = config.get<string>('projectId') ?? '';
  let userId = config.get<string>('userId') ?? '';

  if (!projectId) {
    const entered = await vscode.window.showInputBox({
      title: 'DevFoundry project ID (UUID)',
      prompt: 'Required by the DevFoundry API to submit a task',
      ignoreFocusOut: true,
    });
    if (!entered) {
      return undefined;
    }
    projectId = entered.trim();
    await config.update('projectId', projectId, vscode.ConfigurationTarget.Global);
  }

  if (!userId) {
    const entered = await vscode.window.showInputBox({
      title: 'DevFoundry requesting user ID (UUID)',
      prompt: 'Required by the DevFoundry API to attribute the task',
      ignoreFocusOut: true,
    });
    if (!entered) {
      return undefined;
    }
    userId = entered.trim();
    await config.update('userId', userId, vscode.ConfigurationTarget.Global);
  }

  return { projectId, userId };
}

async function gatherTaskMaterial(): Promise<string | undefined> {
  const source = await vscode.window.showQuickPick(
    [
      { label: 'Current selection', detail: 'Selected text in the active editor' },
      { label: 'Current file', detail: 'Full contents of the active editor' },
      { label: 'Free text', detail: 'Type the task description manually' },
    ],
    { title: 'Delegate a Task — pick the description source' }
  );
  if (!source) {
    return undefined;
  }

  const editor = vscode.window.activeTextEditor;
  if (source.label === 'Current selection') {
    if (!editor || editor.selection.isEmpty) {
      vscode.window.showWarningMessage('No text is selected in the active editor.');
      return undefined;
    }
    return editor.document.getText(editor.selection);
  }

  if (source.label === 'Current file') {
    if (!editor) {
      vscode.window.showWarningMessage('No active editor.');
      return undefined;
    }
    return editor.document.getText();
  }

  const text = await vscode.window.showInputBox({
    title: 'Task description',
    prompt: 'Describe the work to delegate',
    ignoreFocusOut: true,
  });
  return text ?? undefined;
}

export function registerCommands(
  context: vscode.ExtensionContext,
  client: DevFoundryClient,
  tasksProvider: { refresh(): void },
  workspaceInfoProvider: { refresh(): void }
): vscode.Disposable[] {
  const commands: Array<[string, (...args: unknown[]) => unknown]> = [];

  commands.push([
    'devfoundry.connect',
    async () => {
      const email = await vscode.window.showInputBox({
        title: 'DevFoundry sign-in',
        prompt: 'Email',
        ignoreFocusOut: true,
      });
      if (!email) {
        return;
      }
      const password = await vscode.window.showInputBox({
        title: 'DevFoundry sign-in',
        prompt: 'Password',
        password: true,
        ignoreFocusOut: true,
      });
      if (!password) {
        return;
      }
      try {
        await withStatus('Signing in to DevFoundry…', () => client.login(email, password));
        // Smoke test with getTasks; the token lives in SecretStorage and is
        // re-read by the client through the token getter on every request.
        await withStatus('Verifying connection…', () => client.getTasks());
        workspaceInfoProvider.refresh();
        tasksProvider.refresh();
        void vscode.window.showInformationMessage(`Connected to DevFoundry as ${email}.`);
      } catch (err) {
        vscode.window.showErrorMessage(`DevFoundry sign-in failed: ${apiErrorMessage(err)}`);
      }
    },
  ]);

  commands.push([
    'devfoundry.createWorkspace',
    async () => {
      // The first-release API exposes GET /api/workspaces/:id only; workspace
      // registration is done by the installer, not via POST.
      void vscode.window.showInformationMessage(
        'Workspaces are provisioned by the DevFoundry installer. Configure devfoundry.projectId to attach this folder to a project.'
      );
      workspaceInfoProvider.refresh();
    },
  ]);

  commands.push([
    'devfoundry.runTask',
    async () => {
      const material = await gatherTaskMaterial();
      if (material === undefined) {
        return;
      }
      const description = material.trim();
      if (!description) {
        vscode.window.showWarningMessage('The task description is empty.');
        return;
      }

      const preview = truncate(description, PREVIEW_CHARS);
      const confirm = await vscode.window.showWarningMessage(
        `Submit this work to DevFoundry?\n\n"${preview}"`,
        { modal: true, detail: 'The selected material is sent to the customer DevFoundry API as a task description.' },
        'Confirm'
      );
      if (confirm !== 'Confirm') {
        return;
      }

      const owner = await resolveTaskOwner();
      if (!owner) {
        return;
      }

      try {
        const task = await withStatus('Submitting task to DevFoundry…', () =>
          client.createTask(description, owner.projectId, owner.userId)
        );
        tasksProvider.refresh();
        workspaceInfoProvider.refresh();
        void vscode.window.showInformationMessage(`Task submitted: ${task.id}`);
      } catch (err) {
        vscode.window.showErrorMessage(`Task submission failed: ${apiErrorMessage(err)}`);
      }
    },
  ]);

  commands.push([
    'devfoundry.cancelTask',
    async () => {
      try {
        const task = await pickTask(client, 'Cancel Task', true);
        if (!task) {
          return;
        }
        const confirm = await vscode.window.showWarningMessage(
          `Cancel this task?\n\n"${truncate(task.description, PREVIEW_CHARS)}"`,
          { modal: true },
          'Cancel Task'
        );
        if (confirm !== 'Cancel Task') {
          return;
        }
        await withStatus('Cancelling task…', () => client.cancelTask(task.id));
        tasksProvider.refresh();
        workspaceInfoProvider.refresh();
        void vscode.window.showInformationMessage(`Task cancelled: ${task.id}`);
      } catch (err) {
        vscode.window.showErrorMessage(`Cancel failed: ${apiErrorMessage(err)}`);
      }
    },
  ]);

  commands.push([
    'devfoundry.retryTask',
    async () => {
      try {
        const task = await pickTask(client, 'Retry Task');
        if (!task) {
          return;
        }
        await withStatus('Retrying task…', () => client.retryTask(task.id));
        tasksProvider.refresh();
        workspaceInfoProvider.refresh();
        void vscode.window.showInformationMessage(`Task re-queued: ${task.id}`);
      } catch (err) {
        vscode.window.showErrorMessage(`Retry failed: ${apiErrorMessage(err)}`);
      }
    },
  ]);

  commands.push([
    'devfoundry.searchContext',
    async () => {
      const query = await vscode.window.showInputBox({
        title: 'Search Authorized Context',
        prompt: 'Search the authorized context of this installation',
        ignoreFocusOut: true,
      });
      if (!query) {
        return;
      }
      try {
        const { results, notAvailable } = await withStatus('Searching context…', () =>
          client.searchContext(query)
        );
        if (notAvailable) {
          void vscode.window.showInformationMessage(
            'Context search not available on this installation.'
          );
          return;
        }
        if (results.length === 0) {
          void vscode.window.showInformationMessage(`No context matches for "${query}".`);
          return;
        }
        const picked = await vscode.window.showQuickPick(
          results.map((r) => ({
            label: truncate(r.text.replace(/\s+/g, ' ').trim(), 80),
            description: `${r.location}${r.revision ? ` @ ${r.revision}` : ''}`,
            detail: r.id,
          })),
          { title: `Context results for "${query}"`, placeHolder: `${results.length} match(es)` }
        );
        void picked;
      } catch (err) {
        vscode.window.showErrorMessage(`Context search failed: ${apiErrorMessage(err)}`);
      }
    },
  ]);

  commands.push([
    'devfoundry.reviewDiff',
    async () => {
      try {
        const task = await pickTask(client, 'Review Task Diff');
        if (!task) {
          return;
        }
        const { packet } = await withStatus('Loading review packet…', () =>
          client.getReviewPacket(task.id)
        );
        const patch = packet.patch;
        if (typeof patch === 'string' && patch.trim() !== '') {
          const doc = await vscode.workspace.openTextDocument({
            content: patch,
            language: 'diff',
          });
          await vscode.window.showTextDocument(doc, vscode.ViewColumn.Beside);
        } else {
          const doc = await vscode.workspace.openTextDocument({
            content: JSON.stringify(packet, null, 2),
            language: 'json',
          });
          await vscode.window.showTextDocument(doc, vscode.ViewColumn.Beside);
        }
      } catch (err) {
        if (err instanceof DevFoundryApiError && err.status === 404) {
          vscode.window.showInformationMessage(
            'No review packet for this task yet. The packet is generated when the task reaches review.'
          );
          return;
        }
        vscode.window.showErrorMessage(`Review failed: ${apiErrorMessage(err)}`);
      }
    },
  ]);

  commands.push([
    'devfoundry.openConsole',
    async () => {
      const consoleUrl =
        vscode.workspace.getConfiguration('devfoundry').get<string>('consoleUrl') ??
        'http://localhost:3001';
      try {
        await vscode.env.openExternal(vscode.Uri.parse(consoleUrl));
      } catch (err) {
        vscode.window.showErrorMessage(`Cannot open web console: ${apiErrorMessage(err)}`);
      }
    },
  ]);

  return commands
    .map(([id, handler]) => vscode.commands.registerCommand(id, handler))
    .filter((d): d is vscode.Disposable => d !== undefined);
}
