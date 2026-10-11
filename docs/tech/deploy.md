# Deploying DevFoundry

This guide covers deploying the full DevFoundry appliance on a Kubernetes cluster.

## Prerequisites

- A Kubernetes cluster (tested on Run:ai-scheduled DGX/H200 clusters; any K8s works)
- `kubectl` configured against the cluster
- A namespace to deploy into (examples use `runai-dev-foundry`)
- A pull secret for `ghcr.io` named `ghcr-pull` in the namespace (for private images)
- Docker (or compatible) for building/pushing images
- 4 CPU, 8 GB RAM free (API/worker/web are CPU-only)

## Architecture overview

| Component | Image | Port | Node placement |
|---|---|---|---|
| postgres | postgres | 5432 | any |
| api | `ghcr.io/mani-mal/dev-foundry-api` | 3000 | CPU-only |
| web | `ghcr.io/mani-mal/dev-foundry-web` | 3001 | CPU-only |
| worker | `ghcr.io/mani-mal/dev-foundry-worker` | — | CPU-only |
| opencode (harness) | `ghcr.io/mani-mal/devfoundry-opencode` | 4096 | CPU-only |
| routeforge | `ghcr.io/mani-mal/dev-foundry-routeforge` | 8000 | CPU-only |
| contextforge | `ghcr.io/ibm/mcp-context-forge` | 4444 | CPU-only |
| langfuse | langfuse/langfuse | 3000 | CPU-only |

## 1. Create the namespace and pull secret

```bash
kubectl create namespace runai-dev-foundry

kubectl -n runai-dev-foundry create secret docker-registry ghcr-pull \
  --docker-server=ghcr.io \
  --docker-username=<GH_USER> \
  --docker-password=<GH_PAT>
```

## 2. Create the app secrets

Create a secret holding the platform admin password and DB credentials:

```bash
kubectl -n runai-dev-foundry create secret generic devfoundry-secrets \
  --from-literal=PLATFORM_ADMIN_PASSWORD='admin123secure' \
  --from-literal=DATABASE_PASSWORD='devfoundry'
```

## 3. Apply the manifest

The full stack is defined in `k8s/dev-foundry.yaml`:

```bash
kubectl apply -f k8s/dev-foundry.yaml
```

Check that all pods are Running:

```bash
kubectl -n runai-dev-foundry get pods
```

Expected pods: `contextforge-*`, `devfoundry-api-*`, `devfoundry-web-*`, `devfoundry-worker-*`, `langfuse-*`, `opencode-*`, `postgres-0`, `routeforge-*`.

## 4. Verify deployment

Run the verification script:

```bash
bash scripts/verify-deployment.sh
```

Or check health endpoints via port-forward:

```bash
kubectl -n runai-dev-foundry port-forward svc/devfoundry-api 3000:3000 &
curl -s --noproxy '*' http://127.0.0.1:3000/health
```

## Alternative: Docker Compose (single host)

For evaluation on one machine:

```bash
cp .env.example .env    # configure values
docker compose -f docker-compose.yml up -d
```

## Troubleshooting deployment

| Symptom | Likely cause | Fix |
|---|---|---|
| Pod `ImagePullBackOff` | Wrong/missing pull secret | Add explicit `imagePullSecrets: [{name: ghcr-pull}]` — Run:ai auto-injects an NGC secret that 401s |
| Pod `CrashLoopBackOff` | Bad env/config | `kubectl -n runai-dev-foundry logs <pod> --previous` |
| API unreachable | Port-forward died | Re-establish: `kubectl -n runai-dev-foundry port-forward svc/devfoundry-api 3000:3000 &` |
| `sendInput` timeouts | Harness busy | Non-fatal by design — see [Managing the Worker](worker.md) |
