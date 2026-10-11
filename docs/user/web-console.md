# Web Console

The web console runs at `http://<appliance>:3001` (CPU-only deployment). Login page at `/login`.

## Pages

| Page | Purpose |
|---|---|
| Login | Account sign-in |
| Dashboard | Factory overview |
| TasksPage | Task queue, filter by status/phase |
| TaskDetail | Per-task detail, review packet, disposition |
| ProjectConfig | Project settings, repo config |
| ApplianceHealth | Component health (postgres, api, worker, opencode, routeforce, contextforge) |

## Reviewing a task

1. Open **Tasks** page — find the task (status `Pending`, phase `AwaitingReview`)
2. Open **Task Detail**
3. Review the generated review packet (outcomes, evidence, checkpoint)
4. Disposition the task — this moves it to `Completed`

## Health checks

**ApplianceHealth** shows each component's status. If a component is unhealthy:

```bash
kubectl -n runai-dev-foundry logs deploy/<component> --tail=100
```

## Proxy gotcha

If the browser can't reach the appliance, check `http_proxy` settings — localhost traffic must bypass the proxy.
