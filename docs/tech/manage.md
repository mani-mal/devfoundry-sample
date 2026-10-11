# Managing DevFoundry

Day-to-day administrative tasks: managing images, ports, secrets, and access.

## Managing images

### Rebuild and push an image

Images must be built from a committed tree (git archive):

```bash
git add -A && git commit -m "change"

DOCKER="/path/to/docker"
git archive HEAD | $DOCKER build -f packages/worker/Dockerfile -t ghcr.io/mani-mal/dev-foundry-worker:v1.1.7 -
$DOCKER push ghcr.io/mani-mal/dev-foundry-worker:v1.1.7
```

### Deploy a new version

```bash
# Update image tag in k8s/dev-foundry.yaml, then:
kubectl apply -f k8s/dev-foundry.yaml
kubectl -n runai-dev-foundry rollout status deploy/devfoundry-worker --timeout=90s
```

### Rolling restart

```bash
kubectl -n runai-dev-foundry rollout restart deploy/devfoundry-worker
kubectl -n runai-dev-foundry rollout status deploy/devfoundry-worker --timeout=90s
```

## Managing ports and port-forwards

Port-forwards die intermittently (Run:ai sandbox kills them). Before reuse:

```bash
pgrep -f port-forward
```

Re-establish as needed:

```bash
kubectl -n runai-dev-foundry port-forward svc/routeforge 8000:8000 &
kubectl -n runai-dev-foundry port-forward svc/contextforge 4444:4444 &
kubectl -n runai-dev-foundry port-forward svc/opencode 4096:4096 &
kubectl -n runai-dev-foundry port-forward svc/devfoundry-api 3000:3000 &
```

Logs: `/tmp/opencode/pf-*.log`.

## Managing secrets

```bash
kubectl -n runai-dev-foundry get secrets

# Rotate the platform admin password:
kubectl -n runai-dev-foundry patch secret devfoundry-secrets \
  -p '{"stringData":{"PLATFORM_ADMIN_PASSWORD":"newpass"}}'

# Restart pods to pick up the change:
kubectl -n runai-dev-foundry rollout restart deploy/devfoundry-api
```

## Access and authentication

### API login

```bash
curl -s --noproxy '*' -X POST http://127.0.0.1:3000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@devfoundry.local","password":"admin123secure"}'
```

Returns a 92-char bearer token. All `/api/*` routes require `Authorization: Bearer <token>`.

### RouteForge app tokens

RouteForge is fail-closed: missing/invalid token → `invalid_api_key` error. Seeded app tokens (see `routeForge/app/apps/bootstrap.py` SEED_APPS):

| App | Token |
|---|---|
| acme | `acme-key` |
| hospital | `hospital-key` |
| default | `demo-key` |

Usage:

```bash
curl -s --noproxy '*' -H "Authorization: Bearer acme-key" http://127.0.0.1:8000/v1/models
```

### ContextForge

Requires `DEFAULT_USER_PASSWORD` env of at least 12 characters at boot (e.g. `admin123secure!X`).

## Proxy gotcha

If `http_proxy` is set, curl to localhost fails with `EAI_AGAIN`. Always:

```bash
curl --noproxy '*' ...
```

## Verifying task lifecycle

1. Log in and create a task:

```bash
TOKEN=$(curl -s --noproxy '*' -X POST http://127.0.0.1:3000/api/auth/login ... | jq -r .token)
curl -s --noproxy '*' -X POST http://127.0.0.1:3000/api/tasks \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"title":"t","description":"d","projectId":"proj-1","userId":"user-1"}'
```

2. Watch the phase chain: `Submitted → Qualified → Validating → AwaitingReview`

```bash
kubectl -n runai-dev-foundry logs deploy/devfoundry-worker --tail=50 | grep <taskId>
```

3. Inspect stored outcomes in postgres:

```bash
kubectl -n runai-dev-foundry exec -i postgres-0 -- \
  psql -U devfoundry -d devfoundry -c "SELECT task_id, success FROM task_outcomes;"
```

## Logs

```bash
kubectl -n runai-dev-foundry logs deploy/devfoundry-worker --tail=100
kubectl -n runai-dev-foundry logs deploy/devfoundry-api --tail=100
```
