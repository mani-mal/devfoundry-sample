import { Router, Request, Response, NextFunction } from 'express';
import { query } from '../db';
import { authMiddleware, requireRole } from '../auth';

const router = Router();

interface RequestRow {
  id: string;
  org_id: string;
  equipment_id: string;
  title: string;
  description: string | null;
  priority: 'low' | 'medium' | 'high' | 'urgent';
  status: 'open' | 'triaged' | 'converted' | 'closed';
  raised_by: string | null;
  created_at: Date;
  updated_at: Date;
}

interface EquipmentRow {
  id: string;
  org_id: string;
}

const VALID_PRIORITIES = ['low', 'medium', 'high', 'urgent'];

router.use(authMiddleware);

function missingUser(res: Response): boolean {
  res.status(401).json({ error: 'Unauthorized' });
  return true;
}

router.get(
  '/requests',
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        missingUser(res);
        return;
      }
      const { equipmentId, status } = req.query as {
        equipmentId?: string;
        status?: string;
      };
      const conditions: string[] = ['org_id = $1'];
      const params: unknown[] = [req.user.orgId];
      if (equipmentId) {
        conditions.push(`equipment_id = $${params.push(equipmentId)}`);
      }
      if (status) {
        conditions.push(`status = $${params.push(status)}`);
      }
      const result = await query<RequestRow>(
        `SELECT id, org_id, equipment_id, title, description, priority, status, raised_by, created_at, updated_at FROM service_requests WHERE ${conditions.join(' AND ')} ORDER BY created_at DESC`,
        params
      );
      res.json({ requests: result.rows });
    } catch (err) {
      next(err);
    }
  }
);

router.get(
  '/requests/:id',
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        missingUser(res);
        return;
      }
      const result = await query<RequestRow>(
        'SELECT id, org_id, equipment_id, title, description, priority, status, raised_by, created_at, updated_at FROM service_requests WHERE id = $1 AND org_id = $2',
        [req.params.id, req.user.orgId]
      );
      if (result.rows.length === 0) {
        res.status(404).json({ error: 'Not found' });
        return;
      }
      res.json({ request: result.rows[0] });
    } catch (err) {
      next(err);
    }
  }
);

router.post(
  '/requests',
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        missingUser(res);
        return;
      }
      const { equipmentId, title, description, priority } = req.body as {
        equipmentId?: string;
        title?: string;
        description?: string;
        priority?: string;
      };
      if (!equipmentId || !title) {
        res.status(400).json({ error: 'Missing required fields' });
        return;
      }
      if (priority !== undefined && !VALID_PRIORITIES.includes(priority)) {
        res.status(400).json({ error: 'Invalid priority' });
        return;
      }
      const equipment = await query<EquipmentRow>(
        'SELECT id, org_id FROM equipment WHERE id = $1',
        [equipmentId]
      );
      if (equipment.rows.length === 0 || equipment.rows[0].org_id !== req.user.orgId) {
        res.status(400).json({ error: 'Invalid equipment' });
        return;
      }
      const result = await query<RequestRow>(
        'INSERT INTO service_requests (org_id, equipment_id, title, description, priority, raised_by) VALUES ($1, $2, $3, $4, $5, $6) RETURNING id, org_id, equipment_id, title, description, priority, status, raised_by, created_at, updated_at',
        [req.user.orgId, equipmentId, title, description ?? null, priority ?? 'medium', req.user.userId]
      );
      res.status(201).json({ request: result.rows[0] });
    } catch (err) {
      next(err);
    }
  }
);

router.post(
  '/requests/:id/triage',
  requireRole('admin', 'manager'),
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        missingUser(res);
        return;
      }
      const result = await query<RequestRow>(
        "UPDATE service_requests SET status = 'triaged', updated_at = NOW() WHERE id = $1 AND org_id = $2 AND status = 'open' RETURNING id, org_id, equipment_id, title, description, priority, status, raised_by, created_at, updated_at",
        [req.params.id, req.user.orgId]
      );
      if (result.rows.length === 0) {
        const exists = await query<RequestRow>(
          'SELECT id FROM service_requests WHERE id = $1 AND org_id = $2',
          [req.params.id, req.user.orgId]
        );
        if (exists.rows.length === 0) {
          res.status(404).json({ error: 'Not found' });
          return;
        }
        res.status(409).json({ error: 'Invalid transition' });
        return;
      }
      res.json({ request: result.rows[0] });
    } catch (err) {
      next(err);
    }
  }
);

router.post(
  '/requests/:id/close',
  requireRole('admin', 'manager'),
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        missingUser(res);
        return;
      }
      const result = await query<RequestRow>(
        "UPDATE service_requests SET status = 'closed', updated_at = NOW() WHERE id = $1 AND org_id = $2 AND status IN ('open','triaged') RETURNING id, org_id, equipment_id, title, description, priority, status, raised_by, created_at, updated_at",
        [req.params.id, req.user.orgId]
      );
      if (result.rows.length === 0) {
        const exists = await query<RequestRow>(
          'SELECT id FROM service_requests WHERE id = $1 AND org_id = $2',
          [req.params.id, req.user.orgId]
        );
        if (exists.rows.length === 0) {
          res.status(404).json({ error: 'Not found' });
          return;
        }
        res.status(409).json({ error: 'Invalid transition' });
        return;
      }
      res.json({ request: result.rows[0] });
    } catch (err) {
      next(err);
    }
  }
);

router.delete(
  '/requests/:id',
  requireRole('admin'),
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        missingUser(res);
        return;
      }
      const result = await query(
        'DELETE FROM service_requests WHERE id = $1 AND org_id = $2',
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
