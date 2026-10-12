import { Router, Request, Response, NextFunction } from 'express';
import { query } from '../db';
import { authMiddleware, requireRole } from '../auth';

const router = Router();

interface EquipmentRow {
  id: string;
  org_id: string;
  site_id: string;
  name: string;
  serial: string;
  model: string | null;
  installed_at: Date | null;
  status: 'operational' | 'degraded' | 'down' | 'retired';
  created_at: Date;
}

interface SiteRow {
  id: string;
  org_id: string;
}

const VALID_STATUS = ['operational', 'degraded', 'down', 'retired'];

router.use(authMiddleware);

function missingUser(res: Response): boolean {
  res.status(401).json({ error: 'Unauthorized' });
  return true;
}

function invalidStringField(value: unknown): boolean {
  return typeof value !== 'string' || value.trim() === '';
}

router.get(
  '/equipment',
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        missingUser(res);
        return;
      }
      const { siteId } = req.query as { siteId?: string };
      let result;
      if (siteId) {
        result = await query<EquipmentRow>(
          'SELECT id, org_id, site_id, name, serial, model, installed_at, status, created_at FROM equipment WHERE org_id = $1 AND site_id = $2 ORDER BY created_at DESC',
          [req.user.orgId, siteId]
        );
      } else {
        result = await query<EquipmentRow>(
          'SELECT id, org_id, site_id, name, serial, model, installed_at, status, created_at FROM equipment WHERE org_id = $1 ORDER BY created_at DESC',
          [req.user.orgId]
        );
      }
      res.json({ equipment: result.rows });
    } catch (err) {
      next(err);
    }
  }
);

router.get(
  '/equipment/:id',
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        missingUser(res);
        return;
      }
      const result = await query<EquipmentRow>(
        'SELECT id, org_id, site_id, name, serial, model, installed_at, status, created_at FROM equipment WHERE id = $1 AND org_id = $2',
        [req.params.id, req.user.orgId]
      );
      if (result.rows.length === 0) {
        res.status(404).json({ error: 'Not found' });
        return;
      }
      res.json({ equipment: result.rows[0] });
    } catch (err) {
      next(err);
    }
  }
);

router.post(
  '/equipment',
  requireRole('admin', 'manager'),
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        missingUser(res);
        return;
      }
      const { siteId, name, serial, model, installedAt } = req.body as {
        siteId?: string;
        name?: string;
        serial?: string;
        model?: string;
        installedAt?: string;
      };
      if (!siteId || !name || !serial) {
        res.status(400).json({ error: 'Missing required fields' });
        return;
      }
      const site = await query<SiteRow>(
        'SELECT id, org_id FROM customer_sites WHERE id = $1',
        [siteId]
      );
      if (site.rows.length === 0 || site.rows[0].org_id !== req.user.orgId) {
        res.status(400).json({ error: 'Invalid site' });
        return;
      }
      const result = await query<EquipmentRow>(
        'INSERT INTO equipment (org_id, site_id, name, serial, model, installed_at) VALUES ($1, $2, $3, $4, $5, $6) RETURNING id, org_id, site_id, name, serial, model, installed_at, status, created_at',
        [req.user.orgId, siteId, name, serial, model ?? null, installedAt ?? null]
      );
      res.status(201).json({ equipment: result.rows[0] });
    } catch (err) {
      const code = (err as { code?: string }).code;
      if (code === '23505') {
        res.status(409).json({ error: 'Serial already exists' });
        return;
      }
      next(err);
    }
  }
);

router.put(
  '/equipment/:id',
  requireRole('admin', 'manager'),
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        missingUser(res);
        return;
      }
      const { name, model, status, installedAt, siteId } = req.body as {
        name?: string;
        model?: string;
        status?: string;
        installedAt?: string;
        siteId?: string;
      };
      if (status !== undefined && !VALID_STATUS.includes(status)) {
        res.status(400).json({ error: 'Invalid status' });
        return;
      }
      const sets: string[] = [];
      const params: unknown[] = [];
      if (name !== undefined) {
        if (invalidStringField(name)) {
          res.status(400).json({ error: 'Invalid value for name' });
          return;
        }
        sets.push(`name = $${params.push(name)}`);
      }
      if (model !== undefined) {
        sets.push(`model = $${params.push(model)}`);
      }
      if (status !== undefined) {
        sets.push(`status = $${params.push(status)}`);
      }
      if (installedAt !== undefined) {
        sets.push(`installed_at = $${params.push(installedAt)}`);
      }
      if (siteId !== undefined) {
        const site = await query<SiteRow>(
          'SELECT id, org_id FROM customer_sites WHERE id = $1',
          [siteId]
        );
        if (site.rows.length === 0 || site.rows[0].org_id !== req.user.orgId) {
          res.status(400).json({ error: 'Invalid site' });
          return;
        }
        sets.push(`site_id = $${params.push(siteId)}`);
      }
      if (sets.length === 0) {
        res.status(400).json({ error: 'No fields to update' });
        return;
      }
      params.push(req.params.id, req.user.orgId);
      const result = await query<EquipmentRow>(
        `UPDATE equipment SET ${sets.join(', ')} WHERE id = $${params.length - 1} AND org_id = $${params.length} RETURNING id, org_id, site_id, name, serial, model, installed_at, status, created_at`,
        params
      );
      if (result.rows.length === 0) {
        res.status(404).json({ error: 'Not found' });
        return;
      }
      res.json({ equipment: result.rows[0] });
    } catch (err) {
      next(err);
    }
  }
);

router.delete(
  '/equipment/:id',
  requireRole('admin'),
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        missingUser(res);
        return;
      }
      const result = await query(
        'DELETE FROM equipment WHERE id = $1 AND org_id = $2',
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
