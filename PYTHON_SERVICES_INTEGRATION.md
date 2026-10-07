# DevFoundry - Python Services Integration

## Architecture Overview

DevFoundry is an orchestrator that integrates with specialized Python services:

```
┌─────────────────────────────────────────────────────────────┐
│                     DevFoundry UI/API                        │
│                  (Node.js or Python)                         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ├─ HTTP REST API ────────────────────┐
                     │                                    │
                     ▼                                    ▼
        ┌──────────────────────┐          ┌──────────────────────┐
        │   ContextForge       │          │    RouteForge        │
        │   (Python/FastAPI)   │          │    (Python)          │
        │   Port 4444          │          │    Port 8000         │
        │   MCP Gateway        │          │    Model Router      │
        └──────────────────────┘          └──────────────────────┘
                     │                                    │
                     └────────────────┬───────────────────┘
                                      │
                                      ▼
                         ┌──────────────────────┐
                         │   Langfuse           │
                         │   (Python/FastAPI)   │
                         │   Port 3000          │
                         │   Tracing/Evals      │
                         └──────────────────────┘
                                      │
                                      ▼
                         ┌──────────────────────┐
                         │    PostgreSQL        │
                         │    (Shared DB)       │
                         └──────────────────────┘
```

## Integration Pattern

### 1. ContextForge (MCP Gateway)

**Service**: `ghcr.io/ibm/mcp-context-forge:latest` (Python/FastAPI)

**Integration**:
```typescript
// DevFoundry calls ContextForge REST API
const contextForge = axios.create({
  baseURL: process.env.CONTEXFORGE_URL || 'http://localhost:4444',
  headers: {
    'Authorization': `Bearer ${process.env.CONTEXFORGE_TOKEN}`
  }
});

// Get tools from ContextForge
const tools = await contextForge.get('/tools');

// Call a specific tool
const result = await contextForge.post(`/tools/${toolId}/call`, input);
```

### 2. RouteForge (Model Gateway)

**Service**: Clone of `https://github.com/mani-mal/routeForge` (Python)

**Integration**:
```typescript
// DevFoundry calls RouteForge REST API
const routeForge = axios.create({
  baseURL: process.env.ROUTEFORGE_URL || 'http://localhost:8000',
  headers: {
    'Authorization': `Bearer ${process.env.ROUTEFORGE_TOKEN}`
  }
});

// Get model completions
const response = await routeForge.post('/v1/chat/completions', {
  model: 'gpt-4',
  messages: [{ role: 'user', content: task.description }]
});
```

### 3. Langfuse (Tracing)

**Service**: `langfuse/langfuse:latest` (Python/FastAPI)

**Integration**:
```typescript
// DevFoundry sends traces to Langfuse
const langfuse = axios.create({
  baseURL: process.env.LANGFUSE_URL || 'http://localhost:3000',
  headers: {
    'Authorization': `Bearer ${process.env.LANGFUSE_SECRET_KEY}`
  }
});

// Log trace
await langfuse.post('/api/public/traces', {
  traceId: taskId,
  name: 'task-execution',
  input: task,
  output: result
});
```

## Docker Compose Integration

```yaml
services:
  # ContextForge - MCP Gateway (Python)
  contextforge:
    image: ghcr.io/ibm/mcp-context-forge:latest
    ports:
      - "4444:4444"
    environment:
      DATABASE_URL: postgresql://devfoundry:devfoundry@postgres:5432/devfoundry
      JWT_SECRET_KEY: ${JWT_SECRET_KEY}
      AUTH_ENCRYPTION_SECRET: ${AUTH_ENCRYPTION_SECRET}

  # DevFoundry - Orchestrator (Node.js)
  devfoundry-api:
    build: .
    ports:
      - "3000:3000"
    environment:
      CONTEXFORGE_URL: http://contextforge:4444
      ROUTEFORGE_URL: http://routeforge:8000
      LANGFUSE_URL: http://langfuse:3000
```

## Key Points

1. **Don't rewrite Python services** - Use Docker to run them as separate containers
2. **REST API integration** - DevFoundry communicates via HTTP calls
3. **Shared PostgreSQL** - All services can share the same database or use separate databases
4. **DevFoundry is the orchestrator** - Manages workspaces, tasks, skills, validation pipeline
5. **Each service owns its domain** - ContextForge manages MCP tools, RouteForge routes models, DevFoundry manages workflows

## DevFoundry Responsibilities

- Task lifecycle management
- Workspace orchestration  
- Skills catalog and versioning
- Validation pipeline execution
- Review packet generation
- Multi-identity and authorization
- Capacity admission and routing decisions

## Integration Flow

```
User creates task → DevFoundry stores in DB
         ↓
DevFoundry worker fetches task
         ↓
Worker calls ContextForge API to get available tools
         ↓
Worker calls RouteForge API with task + tools
         ↓
RouteForge returns model response
         ↓
Worker stores result in DB
         ↓
Worker calls Langfuse to log trace
         ↓
DevFoundry UI displays result
```

## Benefits of This Approach

1. **Leverage existing projects** - Don't reinvent the wheel
2. **Specialized expertise** - Each project has domain experts
3. **Easier maintenance** - Update services independently
4. **Proven implementations** - Use tested, production-ready code
5. **Flexibility** - Swap services without changing DevFoundry core
