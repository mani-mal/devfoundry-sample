import express, { Request, Response, NextFunction } from 'express';
import { createServer } from 'http';
import { Server } from 'socket.io';
import cors from 'cors';
import { DevFoundryCore } from '@dev-foundry/core';
import { Task, TaskPhase, TaskStatus } from '@dev-foundry/core';
import { createLogger } from '@dev-foundry/core';
import { createSchema, Database } from '@dev-foundry/core';
import { Pool } from 'pg';
import { v4 as uuidv4 } from 'uuid';
import * as dotenv from 'dotenv';

dotenv.config();

const app = express();
const server = createServer(app);
const io = new Server(server, {
  cors: {
    origin: '*',
    methods: ['GET', 'POST']
  }
});

const logger = createLogger('web-console');
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors());
app.use(express.json());

// Health check
app.get('/health', (req: Request, res: Response) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Database connection
let db: Database | null = null;

async function connectDatabase(): Promise<void> {
  const databaseUrl = process.env.DATABASE_URL || 
    'postgres://devfoundry:devfoundry@localhost:5432/devfoundry';
  
  const match = databaseUrl.match(/postgres:\/\/([^:]+):([^@]+)@([^:]+):(\d+)\/(.+)/);
  if (!match) {
    throw new Error('Invalid DATABASE_URL');
  }
  
  const [, username, password, host, port, database] = match;
  db = new Database({
    host,
    port: parseInt(port, 10),
    database,
    username,
    password,
  });
  
  await db.connect();
  logger.info('Connected to database');
}

// API Routes
app.get('/api/tasks', async (req: Request, res: Response) => {
  try {
    if (!db) {
      return res.status(500).json({ error: 'Database not connected' });
    }
    
    const { tenantId, projectId, status, phase, limit = 50, offset = 0 } = req.query;
    
    let query = `
      SELECT t.*, 
             u.email as user_email,
             p.name as project_name
      FROM tasks t
      LEFT JOIN users u ON t.user_id = u.id
      LEFT JOIN projects p ON t.project_id = p.id
      WHERE 1=1
    `;
    const params: any[] = [];
    const conditions: string[] = [];
    
    if (tenantId) {
      conditions.push('t.tenant_id = $' + (params.length + 1));
      params.push(tenantId);
    }
    
    if (projectId) {
      conditions.push('t.project_id = $' + (params.length + 1));
      params.push(projectId);
    }
    
    if (status) {
      conditions.push('t.status = $' + (params.length + 1));
      params.push(status);
    }
    
    if (phase) {
      conditions.push('t.phase = $' + (params.length + 1));
      params.push(phase);
    }
    
    if (conditions.length > 0) {
      query += ' AND ' + conditions.join(' AND ');
    }
    
    query += ' ORDER BY t.created_at DESC LIMIT $' + (params.length + 1) + ' OFFSET $' + (params.length + 2);
    params.push(limit, offset);
    
    const result = await db.query<Task>(query, params);
    
    res.json({
      tasks: result,
      total: result.length,
      limit: parseInt(limit as string),
      offset: parseInt(offset as string)
    });
  } catch (error) {
    logger.error('Error fetching tasks', { error });
    res.status(500).json({ error: 'Failed to fetch tasks' });
  }
});

app.post('/api/tasks', async (req: Request, res: Response) => {
  try {
    if (!db) {
      return res.status(500).json({ error: 'Database not connected' });
    }
    
    const { description, projectId, userId, baseCommit, targetBranch, skills, contextIds } = req.body;
    
    const task: Partial<Task> = {
      id: uuidv4(),
      tenantId: req.headers['x-tenant-id'] as string || 'default',
      projectId,
      userId,
      status: 'Pending',
      phase: 'Submitted',
      description,
      baseCommit,
      targetBranch,
      workspaceId: uuidv4(),
      skills: skills || [],
      contextIds: contextIds || [],
      toolPermissions: [],
      modelRoute: 'default',
      capacityProfile: 'default',
      retryCount: 0,
      createdAt: new Date(),
      updatedAt: new Date()
    };
    
    await db.query(`
      INSERT INTO tasks (
        id, tenant_id, project_id, user_id, status, phase, description,
        base_commit, target_branch, workspace_id, skills, context_ids,
        tool_permissions, model_route, capacity_profile, created_at, updated_at
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
      RETURNING *
    `, [
      task.id, task.tenantId, task.projectId, task.userId, task.status, task.phase,
      task.description, task.baseCommit, task.targetBranch, task.workspaceId,
      JSON.stringify(task.skills), JSON.stringify(task.contextIds),
      JSON.stringify(task.toolPermissions), task.modelRoute, task.capacityProfile,
      task.createdAt, task.updatedAt
    ]);
    
    io.emit('task:created', task);
    
    res.status(201).json(task);
  } catch (error) {
    logger.error('Error creating task', { error });
    res.status(500).json({ error: 'Failed to create task' });
  }
});

app.get('/api/tasks/:taskId', async (req: Request, res: Response) => {
  try {
    if (!db) {
      return res.status(500).json({ error: 'Database not connected' });
    }
    
    const { taskId } = req.params;
    
    const tasks = await db.query<Task>(
      `SELECT * FROM tasks WHERE id = $1`,
      [taskId]
    );
    
    if (tasks.length === 0) {
      return res.status(404).json({ error: 'Task not found' });
    }
    
    res.json(tasks[0]);
  } catch (error) {
    logger.error('Error fetching task', { error });
    res.status(500).json({ error: 'Failed to fetch task' });
  }
});

app.patch('/api/tasks/:taskId', async (req: Request, res: Response) => {
  try {
    if (!db) {
      return res.status(500).json({ error: 'Database not connected' });
    }
    
    const { taskId } = req.params;
    const updates = req.body;
    
    const setFields: string[] = [];
    const values: any[] = [];
    
    if (updates.status) {
      setFields.push('status = $' + (values.length + 1));
      values.push(updates.status);
    }
    
    if (updates.phase) {
      setFields.push('phase = $' + (values.length + 1));
      values.push(updates.phase);
    }
    
    if (updates.outcome) {
      setFields.push('outcome = $' + (values.length + 1));
      values.push(JSON.stringify(updates.outcome));
    }
    
    if (updates.checkpoint) {
      setFields.push('checkpoint = $' + (values.length + 1));
      values.push(JSON.stringify(updates.checkpoint));
    }
    
    if (updates.cancelledAt) {
      setFields.push('cancelled_at = $' + (values.length + 1));
      values.push(updates.cancelledAt);
    }
    
    if (setFields.length === 0) {
      return res.status(400).json({ error: 'No fields to update' });
    }
    
    values.push(taskId);
    
    const query = `
      UPDATE tasks 
      SET ${setFields.join(', ')}, updated_at = NOW()
      WHERE id = $${values.length}
      RETURNING *
    `;
    
    const result = await db.query<Task>(query, values);
    
    if (result.length === 0) {
      return res.status(404).json({ error: 'Task not found' });
    }
    
    io.emit('task:updated', result[0]);
    
    res.json(result[0]);
  } catch (error) {
    logger.error('Error updating task', { error });
    res.status(500).json({ error: 'Failed to update task' });
  }
});

app.delete('/api/tasks/:taskId', async (req: Request, res: Response) => {
  try {
    if (!db) {
      return res.status(500).json({ error: 'Database not connected' });
    }
    
    const { taskId } = req.params;
    
    await db.query(`DELETE FROM tasks WHERE id = $1`, [taskId]);
    
    io.emit('task:cancelled', { taskId });
    
    res.status(204).send();
  } catch (error) {
    logger.error('Error deleting task', { error });
    res.status(500).json({ error: 'Failed to delete task' });
  }
});

app.get('/api/tasks/:taskId/outcomes', async (req: Request, res: Response) => {
  try {
    if (!db) {
      return res.status(500).json({ error: 'Database not connected' });
    }
    
    const { taskId } = req.params;
    
    const outcomes = await db.query(
      `SELECT * FROM task_outcomes WHERE task_id = $1 ORDER BY created_at DESC`,
      [taskId]
    );
    
    res.json({ outcomes });
  } catch (error) {
    logger.error('Error fetching task outcomes', { error });
    res.status(500).json({ error: 'Failed to fetch outcomes' });
  }
});

// Evidence endpoints
app.get('/api/tasks/:taskId/evidence', async (req: Request, res: Response) => {
  try {
    if (!db) {
      return res.status(500).json({ error: 'Database not connected' });
    }
    
    const { taskId } = req.params;
    
    const task = await db.query<Task>(`SELECT outcome FROM tasks WHERE id = $1`, [taskId]);
    
    if (task.length === 0) {
      return res.status(404).json({ error: 'Task not found' });
    }
    
    const evidence = task[0].outcome?.evidence || [];
    res.json({ evidence });
  } catch (error) {
    logger.error('Error fetching evidence', { error });
    res.status(500).json({ error: 'Failed to fetch evidence' });
  }
});

app.post('/api/tasks/:taskId/evidence', async (req: Request, res: Response) => {
  try {
    if (!db) {
      return res.status(500).json({ error: 'Database not connected' });
    }
    
    const { taskId } = req.params;
    const { type, content, provenance } = req.body;
    
    const evidenceItem = {
      id: uuidv4(),
      type,
      content,
      timestamp: new Date().toISOString(),
      provenance: provenance || {}
    };
    
    const task = await db.query<Task>(`SELECT outcome FROM tasks WHERE id = $1`, [taskId]);
    
    if (task.length === 0) {
      return res.status(404).json({ error: 'Task not found' });
    }
    
    const outcome = task[0].outcome || {
      success: false,
      evidence: [],
      traceReferences: []
    };
    
    outcome.evidence = [...(outcome.evidence || []), evidenceItem];
    
    await db.query(
      `UPDATE tasks SET outcome = $1, updated_at = NOW() WHERE id = $2`,
      [JSON.stringify(outcome), taskId]
    );
    
    io.emit('evidence:added', { taskId, evidence: evidenceItem });
    
    res.status(201).json(evidenceItem);
  } catch (error) {
    logger.error('Error adding evidence', { error });
    res.status(500).json({ error: 'Failed to add evidence' });
  }
});

// Project configuration endpoints
app.get('/api/projects/:projectId/config', async (req: Request, res: Response) => {
  try {
    const { projectId } = req.params;
    
    const config = {
      projectId,
      repositories: [],
      tools: [],
      skills: [],
      contextStatus: {
        lastSync: null,
        status: 'ready'
      }
    };
    
    res.json(config);
  } catch (error) {
    logger.error('Error fetching project config', { error });
    res.status(500).json({ error: 'Failed to fetch config' });
  }
});

app.patch('/api/projects/:projectId/config', async (req: Request, res: Response) => {
  try {
    const { projectId } = req.params;
    const updates = req.body;
    
    res.json({ projectId, ...updates });
  } catch (error) {
    logger.error('Error updating project config', { error });
    res.status(500).json({ error: 'Failed to update config' });
  }
});

// Appliance health endpoints
app.get('/api/health', async (req: Request, res: Response) => {
  try {
    const health = {
      services: {
        api: { status: 'healthy', uptime: process.uptime() },
        worker: { status: 'healthy', tasksProcessed: 0 },
        database: { status: 'healthy', connections: 0 },
        routeforge: { status: 'healthy', lastCheck: new Date().toISOString() },
        contextForge: { status: 'healthy', lastCheck: new Date().toISOString() },
        langfuse: { status: 'healthy', lastCheck: new Date().toISOString() }
      },
      resources: {
        cpu: { usage: 0, cores: 4 },
        memory: { usage: 0, total: 16 },
        disk: { usage: 0, total: 100 }
      }
    };
    
    res.json(health);
  } catch (error) {
    logger.error('Error fetching health', { error });
    res.status(500).json({ error: 'Failed to fetch health' });
  }
});

// Event streaming via WebSocket
io.on('connection', (socket) => {
  logger.info('Client connected', { socketId: socket.id });
  
  socket.emit('connected', { timestamp: new Date().toISOString() });
  
  socket.on('subscribe:tasks', (filters?: { tenantId?: string; projectId?: string }) => {
    socket.join('tasks');
    logger.info('Subscribed to tasks', { socketId: socket.id, filters });
  });
  
  socket.on('subscribe:events', () => {
    socket.join('events');
    logger.info('Subscribed to events', { socketId: socket.id });
  });
  
  socket.on('task:cancel', async (data: { taskId: string }) => {
    const { taskId } = data;
    
    if (!db) {
      socket.emit('task:cancel:error', { error: 'Database not connected' });
      return;
    }
    
    try {
      await db.query(
        `UPDATE tasks SET status = $1, phase = $2, cancelled_at = NOW(), updated_at = NOW() WHERE id = $3`,
        ['Cancelled', 'Cancelled', taskId]
      );
      
      io.emit('task:cancelled', { taskId });
      socket.emit('task:cancel:success', { taskId });
    } catch (error) {
      logger.error('Error cancelling task', { error });
      socket.emit('task:cancel:error', { error: 'Failed to cancel task' });
    }
  });
  
  socket.on('task:resume', async (data: { taskId: string }) => {
    const { taskId } = data;
    
    if (!db) {
      socket.emit('task:resume:error', { error: 'Database not connected' });
      return;
    }
    
    try {
      await db.query(
        `UPDATE tasks SET status = $1, phase = $2, updated_at = NOW() WHERE id = $3`,
        ['Pending', 'Qualified', taskId]
      );
      
      io.emit('task:resumed', { taskId });
      socket.emit('task:resume:success', { taskId });
    } catch (error) {
      logger.error('Error resuming task', { error });
      socket.emit('task:resume:error', { error: 'Failed to resume task' });
    }
  });
  
  socket.on('disconnect', () => {
    logger.info('Client disconnected', { socketId: socket.id });
  });
});

// Serve static files (frontend)
const path = require('path');
app.use(express.static(path.join(__dirname, 'public')));

app.get('/', (req: Request, res: Response) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Start server
async function startServer() {
  try {
    await connectDatabase();
    
    server.listen(PORT, () => {
      logger.info(`Web console started on port ${PORT}`);
      console.log(`Web console available at http://localhost:${PORT}`);
    });
  } catch (error) {
    logger.error('Failed to start server', { error });
    process.exit(1);
  }
}

startServer();
