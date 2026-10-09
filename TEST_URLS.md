# DevFoundry Complete Deployment - Test URLs

## All Services Running ✓

| Service | Local Port | URL | Status |
|---------|-----------|-----|--------|
| **DevFoundry Web UI** | 3001 | **http://localhost:3001** | Running ✓ |
| DevFoundry API | 3000 | http://localhost:3000 | Running ✓ |
| DevFoundry Worker | 3002 | http://localhost:3002 | Running ✓ |
| ContextForge | 4444 | http://localhost:4444 | Running ✓ |
| RouteForge | 8000 | http://localhost:8000 | Running ✓ |
| Langfuse | 3000 | http://localhost:3000 | Running ✓ |

## Port-Forwarding Commands

Open a new terminal and run:

```bash
kubectl -n runai-dev-foundry port-forward svc/devfoundry-web 3001:3000
```

Then open **http://localhost:3001** in your browser.

## DevFoundry Admin UI Features

The web console provides:

### 1. Tasks/Review Page
- View all tasks with phases: Submitted, Qualified, Running, Validating, AwaitingReview, Completed, Failed, Cancelled, Paused
- Filter tasks by status and phase
- Task details with execution location, actor, repo, current phase
- Resource consumption display
- Evidence/artifacts review
- Cancellation, retry, and resume controls

### 2. Project Configuration
- Repository management
- Approved gateway/model aliases
- Tools configuration
- Skills management
- Context status

### 3. Appliance Health
- CPU/RAM/GPU resource usage charts
- Service health status
- PostgreSQL status
- Hardware profile detection

## How to Use

1. Start port-forwarding: `kubectl -n runai-dev-foundry port-forward svc/devfoundry-web 3001:3000`
2. Open http://localhost:3001 in your browser
3. Default credentials: admin/devfoundry (use the secrets from devfoundry-secrets)
4. Navigate to Tasks, Project Config, or Appliance Health

## Architecture Summary

DevFoundry integrates the following Python services via REST API:

- **ContextForge** (Python/FastAPI) - MCP Gateway on port 4444
- **RouteForge** (Python) - Model Gateway on port 8000
- **OpenCode** (Python) - Agent Framework
- **Langfuse** (Python) - Tracing/Evals on port 3000

The DevFoundry Web UI (React) provides the admin interface for managing tasks, projects, and infrastructure.
