name: DevFoundry

description: |
  DevFoundry is an on-premises software factory that orchestrates specialized services.
  It integrates with Python-based gateway services (ContextForge, RouteForge) via HTTP APIs.
  DevFoundry itself can be implemented in Node.js or Python - the key is integration, not replacement.

key_points:
  - ContextForge is a Python FastAPI application (mcp-context-forge)
  - RouteForge is a Python application for model routing
  - DevFoundry should INTEGRATE these services, not rewrite them
  - Use Docker Compose to run all services together
  - DevFoundry API calls ContextForge/RouteForge REST endpoints
  - DevFoundry orchestrates: workspaces, tasks, skills, validation

architecture:
  DevFoundry (Node.js/Python)
    │
    ├─ HTTP API ─→ ContextForge (Python/FastAPI) - MCP gateway
    ├─ HTTP API ─→ RouteForge (Python) - Model routing
    ├─ HTTP API ─→ Langfuse (Python) - Tracing/evals
    ├─ PostgreSQL - Shared database
    └─ Docker Compose - Orchestrates all services

deployment:
  docker-compose:
    - devfoundry: DevFoundry service (port 3000)
    - contextforge: ContextForge gateway (port 4444)
    - routeforge: RouteForge model gateway (port 8000)
    - langfuse: Langfuse tracing (port 3000)
    - postgres: PostgreSQL (port 5432)
    - redis: Redis for caching (port 6379)

integration_pattern:
  When user creates a task in DevFoundry:
  1. DevFoundry stores task in PostgreSQL
  2. DevFoundry worker picks up task
  3. Worker calls ContextForge REST API to get tools
  4. Worker calls RouteForge REST API for model inference
  5. Worker stores results back in PostgreSQL
  6. DevFoundry API serves results to UI
