# DevFoundry VS Code extension

Thin client for the customer-owned DevFoundry API. It is an independent package (not a workspace member).

## Install

```bash
cd extensions/vscode
npm install
npm run compile
```

Package with `vsce package` when a `.vsix` is needed; no Marketplace connection is required for offline distribution.

## Connect

1. Set `devfoundry.url` (default `http://localhost:3000`) to your installation's API base URL.
2. Run **DevFoundry: Connect to DevFoundry** from the Command Palette, enter your email and password.
3. The token is stored in VS Code SecretStorage (`devfoundry.token`) — never in settings, URLs or task text.

## Delegate a task

Run **DevFoundry: Delegate a Task**. Pick the material: current selection, current file, or free text. A transfer preview shows the first 200 characters before you confirm. The task is submitted to `POST /api/tasks` with the configured project and user IDs (`devfoundry.projectId`, `devfoundry.userId` — prompted and saved on first use, the API requires both). The Tasks view streams status; **Cancel Task** / **Retry Task** operate on the selected task.

## Review a diff

Run **DevFoundry: Review Task Diff**. If the review packet contains a patch (the worker's `git diff`), it opens beside the active editor as a diff document; otherwise the packet JSON is shown. Applying the patch is manual — apply it only when its base matches your worktree.

## Commands

| Command | Title |
|---|---|
| `devfoundry.connect` | Connect to DevFoundry |
| `devfoundry.createWorkspace` | Create Workspace |
| `devfoundry.runTask` | Delegate a Task |
| `devfoundry.cancelTask` | Cancel Task |
| `devfoundry.retryTask` | Retry Task |
| `devfoundry.searchContext` | Search Authorized Context |
| `devfoundry.reviewDiff` | Review Task Diff |
| `devfoundry.openConsole` | Open Web Console |

Context search uses `GET /api/context/search?q=...`; if the installation does not expose the route, the extension shows "Context search not available on this installation".

## Enforcement limit

This extension only talks to the DevFoundry API; it is a thin console. Policy enforcement (tool scopes, egress, model access) lives in the harness/worker and the backend gateways. Unmanaged local shell access bypasses DevFoundry gateways entirely — gateway policy cannot constrain an unmanaged local harness (see architecture §12, local integration vs managed execution).
