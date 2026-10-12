import { Router, Request, Response, NextFunction } from 'express';
import { query, pool } from '../db';
import { authMiddleware, requireRole } from '../auth';

const router = Router();

interface WorkOrderRow {
  id: string;
  org_id: string;
  code: string;
  title: string;
  description: string | null;
  type: 'corrective' | 'preventive' | 'inspection';
  priority: 'low' | 'medium' | 'high' | 'urgent';
  status: 'draft' | 'scheduled' | 'in_progress' | 'blocked' | 'completed' | 'cancelled';
  assigned_technician_id: string | null;
  site_id: string;
  equipment_id: string;
  service_request_id: string | null;
  scheduled_for: Date | null;
  created_at: Date;
  updated_at: Date;
}

interface RequestRow {
  id: string;
  org_id: string;
  equipment_id: string;
  title: string;
  description: string | null;
  priority: 'low' | 'medium' | 'high' | 'urgent';
  status: 'open' | 'triaged' | 'converted' | 'closed';
  created_at: Date;
  updated_at: Date;
}

interface OrgScopedRow {
  id: string;
  org_id: string;
}

interface UserCheckRow {
  id: string;
  org_id: string;
  role: string;
}

const TRANSITIONS: Record<string, string[]> = {
  draft: ['scheduled', 'cancelled'],
  scheduled: ['in_progress', 'cancelled'],
  in_progress: ['blocked', 'completed', 'cancelled'],
  blocked: ['in_progress', 'cancelled'],
  completed: [],
  cancelled: [],
};

const WO_COLUMNS =
  'id, org_id, code, title, description, type, priority, status, assigned_technician_id, site_id, equipment_id, service_request_id, scheduled_for, created_at, updated_at';

const VALID_TYPES = ['corrective', 'preventive', 'inspection'];
const VALID_PRIORITIES = ['low', 'medium', 'high', 'urgent'];

const TECHNICIAN_ALLOWED: Record<string, string[]> = {
  in_progress: ['blocked', 'completed'],
};

router.use(authMiddleware);

function missingUser(res: Response): boolean {
  res.status(401).json({ error: 'Unauthorized' });
  return true;
}

async function validateTechnician(
  technicianId: string,
  orgId: string
): Promise<UserCheckRow | null> {
  const result = await query<UserCheckRow>(
    'SELECT id, org_id, role FROM users WHERE id = $1',
    [technicianId]
  );
  const user = result.rows[0];
  if (!user || user.org_id !== orgId || user.role !== 'technician') {
    return null;
  }
  return user;
}

async function nextCode(orgId: string): Promise<string> {
  const result = await query<{ n: string }>(
    "SELECT COALESCE(MAX(CAST(SPLIT_PART(code, '-', 3) AS INT)), 0) + 1 AS n FROM work_orders WHERE org_id = $1 AND SPLIT_PART(code, '-', 3) ~ '^[0-9]+$'",
    [orgId]
  );
  const n = parseInt(result.rows[0].n, 10);
  return `WO-2026-${String(n).padStart(4, '0')}`;
}

router.get(
  '/workorders',
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        missingUser(res);
        return;
      }
      const { status, assignedTo, equipmentId } = req.query as {
        status?: string;
        assignedTo?: string;
        equipmentId?: string;
      };
      const conditions: string[] = ['org_id = $1'];
      const params: unknown[] = [req.user.orgId];
      if (status) {
        conditions.push(`status = $${params.push(status)}`);
      }
      if (assignedTo === 'me') {
        conditions.push(`assigned_technician_id = $${params.push(req.user.userId)}`);
      }
      if (equipmentId) {
        conditions.push(`equipment_id = $${params.push(equipmentId)}`);
      }
      const result = await query<WorkOrderRow>(
        `SELECT ${WO_COLUMNS} FROM work_orders WHERE ${conditions.join(' AND ')} ORDER BY created_at DESC`,
        params
      );
      res.json({ workOrders: result.rows });
    } catch (err) {
      next(err);
    }
  }
);

router.get(
  '/workorders/:id',
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        missingUser(res);
        return;
      }
      const result = await query<WorkOrderRow>(
        `SELECT ${WO_COLUMNS} FROM work_orders WHERE id = $1 AND org_id = $2`,
        [req.params.id, req.user.orgId]
      );
      if (result.rows.length === 0) {
        res.status(404).json({ error: 'Not found' });
        return;
      }
      res.json({ workOrder: result.rows[0] });
    } catch (err) {
      next(err);
    }
  }
);

router.post(
  '/workorders',
  requireRole('admin', 'manager'),
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        missingUser(res);
        return;
      }
      const {
        siteId,
        equipmentId,
        title,
        description,
        type,
        priority,
        assignedTechnicianId,
        scheduledFor,
        serviceRequestId,
      } = req.body as {
        siteId?: string;
        equipmentId?: string;
        title?: string;
        description?: string;
        type?: string;
        priority?: string;
        assignedTechnicianId?: string;
        scheduledFor?: string;
        serviceRequestId?: string;
      };
      if (!siteId || !equipmentId || !title) {
        res.status(400).json({ error: 'Missing required fields' });
        return;
      }
      if (type !== undefined && !VALID_TYPES.includes(type)) {
        res.status(400).json({ error: 'Invalid type' });
        return;
      }
      if (priority !== undefined && !VALID_PRIORITIES.includes(priority)) {
        res.status(400).json({ error: 'Invalid priority' });
        return;
      }
      const site = await query<OrgScopedRow>(
        'SELECT id, org_id FROM customer_sites WHERE id = $1',
        [siteId]
      );
      if (site.rows.length === 0 || site.rows[0].org_id !== req.user.orgId) {
        res.status(400).json({ error: 'Invalid site' });
        return;
      }
      const equipment = await query<OrgScopedRow>(
        'SELECT id, org_id FROM equipment WHERE id = $1',
        [equipmentId]
      );
      if (equipment.rows.length === 0 || equipment.rows[0].org_id !== req.user.orgId) {
        res.status(400).json({ error: 'Invalid equipment' });
        return;
      }
      if (assignedTechnicianId) {
        const tech = await validateTechnician(assignedTechnicianId, req.user.orgId);
        if (!tech) {
          res.status(400).json({ error: 'Invalid technician' });
          return;
        }
      }
      const client = await pool.connect();
      try {
        await client.query('BEGIN');
        const code = await nextCode(req.user.orgId);
        const result = await client.query<WorkOrderRow>(
          `INSERT INTO work_orders (org_id, code, title, description, type, priority, assigned_technician_id, site_id, equipment_id, service_request_id, scheduled_for) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) RETURNING ${WO_COLUMNS}`,
          [
            req.user.orgId,
            code,
            title,
            description ?? null,
            type ?? 'corrective',
            priority ?? 'medium',
            assignedTechnicianId ?? null,
            siteId,
            equipmentId,
            serviceRequestId ?? null,
            scheduledFor ?? null,
          ]
        );
        await client.query('COMMIT');
        res.status(201).json({ workOrder: result.rows[0] });
      } catch (err) {
        await client.query('ROLLBACK');
        throw err;
      } finally {
        client.release();
      }
    } catch (err) {
      next(err);
    }
  }
);

router.post(
  '/workorders/convert/:requestId',
  requireRole('admin', 'manager'),
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        missingUser(res);
        return;
      }
      const { siteId, assignedTechnicianId, scheduledFor } = req.body as {
        siteId?: string;
        assignedTechnicianId?: string;
        scheduledFor?: string;
      };
      const requestResult = await query<RequestRow>(
        'SELECT id, org_id, equipment_id, title, description, priority, status, created_at, updated_at FROM service_requests WHERE id = $1 AND org_id = $2',
        [req.params.requestId, req.user.orgId]
      );
      const svcRequest = requestResult.rows[0];
      if (!svcRequest) {
        res.status(404).json({ error: 'Not found' });
        return;
      }
      if (svcRequest.status === 'converted') {
        res.status(409).json({ error: 'Request already converted' });
        return;
      }
      if (assignedTechnicianId) {
        const tech = await validateTechnician(assignedTechnicianId, req.user.orgId);
        if (!tech) {
          res.status(400).json({ error: 'Invalid technician' });
          return;
        }
      }
      let targetSiteId = siteId ?? null;
      if (targetSiteId) {
        const site = await query<OrgScopedRow>(
          'SELECT id, org_id FROM customer_sites WHERE id = $1',
          [targetSiteId]
        );
        if (site.rows.length === 0 || site.rows[0].org_id !== req.user.orgId) {
          res.status(400).json({ error: 'Invalid site' });
          return;
        }
      }
      const client = await pool.connect();
      try {
        await client.query('BEGIN');
        if (!targetSiteId) {
          const equipSite = await client.query<{ site_id: string }>(
            'SELECT site_id FROM equipment WHERE id = $1',
            [svcRequest.equipment_id]
          );
          targetSiteId = equipSite.rows[0].site_id;
        }
        const codeResult = await client.query<{ n: string }>(
          "SELECT COALESCE(MAX(CAST(SPLIT_PART(code, '-', 3) AS INT)), 0) + 1 AS n FROM work_orders WHERE org_id = $1 AND SPLIT_PART(code, '-', 3) ~ '^[0-9]+$'",
          [req.user.orgId]
        );
        const code = `WO-2026-${String(parseInt(codeResult.rows[0].n, 10)).padStart(4, '0')}`;
        const woResult = await client.query<WorkOrderRow>(
          `INSERT INTO work_orders (org_id, code, title, description, type, priority, assigned_technician_id, site_id, equipment_id, service_request_id, scheduled_for) VALUES ($1, $2, $3, $4, 'corrective', $5, $6, $7, $8, $9, $10) RETURNING ${WO_COLUMNS}`,
          [
            req.user.orgId,
            code,
            svcRequest.title,
            svcRequest.description,
            svcRequest.priority,
            assignedTechnicianId ?? null,
            targetSiteId,
            svcRequest.equipment_id,
            svcRequest.id,
            scheduledFor ?? null,
          ]
        );
        const reqUpdate = await client.query<RequestRow>(
          "UPDATE service_requests SET status = 'converted', updated_at = NOW() WHERE id = $1 AND org_id = $2 AND status <> 'converted' RETURNING id, org_id, equipment_id, title, description, priority, status, created_at, updated_at",
          [svcRequest.id, req.user.orgId]
        );
        if (reqUpdate.rows.length === 0) {
          await client.query('ROLLBACK');
          res.status(409).json({ error: 'Request already converted' });
          return;
        }
        await client.query('COMMIT');
        res.status(201).json({ workOrder: woResult.rows[0], request: reqUpdate.rows[0] });
      } catch (err) {
        await client.query('ROLLBACK');
        throw err;
      } finally {
        client.release();
      }
    } catch (err) {
      next(err);
    }
  }
);

router.post(
  '/workorders/:id/status',
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        missingUser(res);
        return;
      }
      const { status } = req.body as { status?: string };
      if (!status) {
        res.status(400).json({ error: 'Missing required fields' });
        return;
      }
      const existing = await query<WorkOrderRow>(
        `SELECT ${WO_COLUMNS} FROM work_orders WHERE id = $1 AND org_id = $2`,
        [req.params.id, req.user.orgId]
      );
      const wo = existing.rows[0];
      if (!wo) {
        res.status(404).json({ error: 'Not found' });
        return;
      }
      const allowed = TRANSITIONS[wo.status] ?? [];
      if (!allowed.includes(status)) {
        res.status(409).json({ error: 'Invalid transition' });
        return;
      }
      if (req.user.role === 'technician') {
        if (wo.assigned_technician_id !== req.user.userId) {
          res.status(404).json({ error: 'Not found' });
          return;
        }
        const techAllowed = (TECHNICIAN_ALLOWED[wo.status] ?? []).includes(status);
        if (!techAllowed) {
          res.status(403).json({ error: 'Forbidden' });
          return;
        }
      }
      const result = await query<WorkOrderRow>(
        `UPDATE work_orders SET status = $1, updated_at = NOW() WHERE id = $2 AND org_id = $3 RETURNING ${WO_COLUMNS}`,
        [status, req.params.id, req.user.orgId]
      );
      res.json({ workOrder: result.rows[0] });
    } catch (err) {
      next(err);
    }
  }
);

router.put(
  '/workorders/:id',
  requireRole('admin', 'manager'),
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        missingUser(res);
        return;
      }
      const { title, description, priority, type, scheduledFor, assignedTechnicianId } =
        req.body as {
          title?: string;
          description?: string;
          priority?: string;
          type?: string;
          scheduledFor?: string;
          assignedTechnicianId?: string;
        };
      if (type !== undefined && !VALID_TYPES.includes(type)) {
        res.status(400).json({ error: 'Invalid type' });
        return;
      }
      if (priority !== undefined && !VALID_PRIORITIES.includes(priority)) {
        res.status(400).json({ error: 'Invalid priority' });
        return;
      }
      const sets: string[] = [];
      const params: unknown[] = [];
      if (title !== undefined) {
        sets.push(`title = $${params.push(title)}`);
      }
      if (description !== undefined) {
        sets.push(`description = $${params.push(description)}`);
      }
      if (priority !== undefined) {
        sets.push(`priority = $${params.push(priority)}`);
      }
      if (type !== undefined) {
        sets.push(`type = $${params.push(type)}`);
      }
      if (scheduledFor !== undefined) {
        sets.push(`scheduled_for = $${params.push(scheduledFor)}`);
      }
      if (assignedTechnicianId !== undefined) {
        const tech = await validateTechnician(assignedTechnicianId, req.user.orgId);
        if (!tech) {
          res.status(400).json({ error: 'Invalid technician' });
          return;
        }
        sets.push(`assigned_technician_id = $${params.push(assignedTechnicianId)}`);
      }
      if (sets.length === 0) {
        res.status(400).json({ error: 'No fields to update' });
        return;
      }
      params.push(req.params.id, req.user.orgId);
      const result = await query<WorkOrderRow>(
        `UPDATE work_orders SET ${sets.join(', ')} WHERE id = $${params.length - 1} AND org_id = $${params.length} RETURNING ${WO_COLUMNS}`,
        params
      );
      if (result.rows.length === 0) {
        res.status(404).json({ error: 'Not found' });
        return;
      }
      res.json({ workOrder: result.rows[0] });
    } catch (err) {
      next(err);
    }
  }
);

router.delete(
  '/workorders/:id',
  requireRole('admin'),
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        missingUser(res);
        return;
      }
      const result = await query(
        'DELETE FROM work_orders WHERE id = $1 AND org_id = $2',
        [req.params.id, req.user.orgId]
      );
      if (result.rowCount === 0) {
        res.status(404).json({ error: 'Not found' });
        return;
      }
      res.status(204).send();
    } catch (err) {
      next(err);
    }
  }
);

export default router;
