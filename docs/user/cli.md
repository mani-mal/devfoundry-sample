# CLI Reference

The DevFoundry CLI (`devfoundry`) is built on `commander`. Commands:

## auth

```bash
devfoundry auth login        # log in, get bearer token
```

## project

```bash
devfoundry project create --name <name> --repo-url <url> [--default-branch main]
devfoundry project status <name>
```

## task

```bash
devfoundry task list [--status <status>] [--phase <phase>]
devfoundry task create <description> \
  [--project-id <id>] [--user-id <id>] [--model-route <route>]
devfoundry task status <taskId>
devfoundry task cancel <taskId>
```

Lifecycle: `Submitted → Qualified → Validating → AwaitingReview`.

## skill

```bash
devfoundry skill list
devfoundry skill install <skillId> \
  [--version 1.0.0] [--git-repo <url>] [--git-commit HEAD] \
  [--path <path>] [--description <text>] [--status draft]
```

Statuses: `draft | approved | deprecated`.

## tools

```bash
devfoundry tools search <query>
devfoundry tools describe <toolId>
devfoundry tools call <toolId> <input JSON string>
```

`tools call` invokes a ContextForge tool; input must be a valid JSON string.

## HTTP API equivalent

All CLI operations map to `/api/*` routes with `Authorization: Bearer <token>`:

| CLI | API |
|---|---|
| `task list` | `GET /api/tasks` |
| `task create` | `POST /api/tasks` |
| `task status` | `GET /api/tasks/:id` |
| `task cancel` | `PATCH /api/tasks/:id` |
| `tools search` | `GET /api/tools/search?q=` |
| `tools call` | `POST /api/tools/call` |
