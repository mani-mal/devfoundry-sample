# HTTP API Reference

All routes are under `/api/*` (NOT `/v1/*`) and require `Authorization: Bearer <token>` (92-char token from login).

## Login

```bash
POST /api/auth/login
{"email":"admin@devfoundry.local","password":"admin123secure"}

→ {"token":"..."}
```

## Tasks

```bash
GET  /api/tasks                     # list (filter: ?status=&projectId=)
POST /api/tasks                     # create
GET  /api/tasks/:id                 # status
PATCH /api/tasks/:id                # update
```

POST requires `description`, `projectId`, `userId`.

PATCH accepts: `status`, `phase`, `outcome`, `checkpoint`, `completedAt`, `startedAt`, `retryCount`.

Task outcomes & evidence:

```bash
GET  /api/tasks/:id/outcomes
GET  /api/tasks/:id/evidence
```

## Lifecycle

```
Submitted → Qualified → Validating → AwaitingReview → (human) → Completed
```

## Database constraint

`tasks.workspace_id` is `UUID NOT NULL`. OpenCode session ids (`ses_...`) must NOT go there — store them in the checkpoint JSONB (`checkpoint.workspaceId`).

## Third-party services

### RouteForge

```bash
curl -s --noproxy '*' -H "Authorization: Bearer acme-key" http://127.0.0.1:8000/v1/models
```

Auth is app-token fail-closed (`invalid_api_key` on missing/invalid).

### ContextForge

`ghcr.io/ibm/mcp-context-forge` on :4444. Requires `DEFAULT_USER_PASSWORD` ≥12 chars at boot. Tools: `listTools()`, `getTool(id)`, `call(id, input)`.
