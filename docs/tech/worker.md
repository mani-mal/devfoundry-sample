# Managing the Worker

The worker consumes tasks from the queue and drives them through the lifecycle phases by calling the OpenCode harness, RouteForge, and ContextForge.

## Worker lifecycle

For each task the worker executes phase handlers:

```
Submitted   → qualify the task (probe repo, verify tools)
Qualified   → create OpenCode workspace + session, send task to harness
Running     → resume interrupted sessions
Validating  → run lint/tests/security scan, collect evidence
AwaitingReview → generate review packet, record trace reference
```

The lifecycle chain is `Submitted → Qualified → Validating → AwaitingReview`; the human disposition moves it to `Completed`.

## Configuring the worker

```ts
new DevFoundryWorker({
  database,           // pg pool
  openCodeUrl,        // OpenCode harness base URL (port 4096)
  routeForgeUrl,      // RouteForge base URL (port 8000)
  contextForgeUrl,    // ContextForge base URL (port 4444)
  workerId,           // unique worker id
});
```

## Harness execution is fire-and-forget

`sendInput` is non-fatal by design: the OpenCode harness runs asynchronously and may exceed the 120s adapter timeout. The worker logs a warning (`Harness task execution failed (non-fatal)`) and continues; validation later queries progress through the shell.

## Poll loop

The poll loop re-processes tasks whose phase is still actionable. **Known wart:** tasks in `AwaitingReview` are re-processed (20 review packets instead of 1) — a terminal-state guard is a known TODO.

## Forcing task states via PATCH

Use the API to move a task:

```bash
TOKEN=$(...)
curl -s --noproxy '*' -X PATCH http://127.0.0.1:3000/api/tasks/<taskId> \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"status":"Pending","phase":"Validating"}'
```

Accepted PATCH fields: `status`, `phase`, `outcome`, `checkpoint`, `completedAt`, `startedAt`, `retryCount`.

## Database constraint

`tasks.workspace_id` is a `UUID NOT NULL` column. OpenCode session ids (`ses_...`) must NOT be written there — store them inside the checkpoint JSONB as `checkpoint.workspaceId`.

## Troubleshooting the worker

| Symptom | Likely cause | Fix |
|---|---|---|
| Task failed with `invalid input syntax for type uuid` | `ses_...` written to workspace_id | Fixed in v1.1.6 — verify image version |
| Harness task execution failed | Harness timeout (120s) | Non-fatal — ignore, or scale harness replicas |
| No review packets | Poll loop not running | Check worker logs for `Processing task` |
| Evidence arrays empty | Scanner output empty | Cosmetic wart — rows still record |
