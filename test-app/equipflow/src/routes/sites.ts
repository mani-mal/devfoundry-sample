import { Router, Request, Response, NextFunction } from 'express';
import { query } from '../db';
import { authMiddleware, requireRole } from '../auth';

const router = Router();

interface SiteRow {
  id: string;
  org_id: string;
  name: string;
  address: string;
  city: string;
  region: string | null;
  created_at: Date;
}

router.use(authMiddleware);

function missingUser(res: Response): boolean {
  res.status(401).json({ error: 'Unauthorized' });
  return true;
}

function invalidStringField(value: unknown): boolean {
  return typeof value !== 'string' || value.trim() === '';
}

router.get(
  '/sites',
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        missingUser(res);
        return;
      }
      const result = await query<SiteRow>(
        'SELECT id, org_id, name, address, city, region, created_at FROM customer_sites WHERE org_id = $1 ORDER BY created_at DESC',
        [req.user.orgId]
      );
      res.json({ sites: result.rows });
    } catch (err) {
      next(err);
    }
  }
);

router.get(
  '/sites/:id',
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        missingUser(res);
        return;
      }
      const result = await query<SiteRow>(
        'SELECT id, org_id, name, address, city, region, created_at FROM customer_sites WHERE id = $1 AND org_id = $2',
        [req.params.id, req.user.orgId]
      );
      if (result.rows.length === 0) {
        res.status(404).json({ error: 'Not found' });
        return;
      }
      res.json({ site: result.rows[0] });
    } catch (err) {
      next(err);
    }
  }
);

router.post(
  '/sites',
  requireRole('admin', 'manager'),
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        missingUser(res);
        return;
      }
      const { name, address, city, region } = req.body as {
        name?: string;
        address?: string;
        city?: string;
        region?: string;
      };
      if (!name || !address || !city) {
        res.status(400).json({ error: 'Missing required fields' });
        return;
      }
      const result = await query<SiteRow>(
        'INSERT INTO customer_sites (org_id, name, address, city, region) VALUES ($1, $2, $3, $4, $5) RETURNING id, org_id, name, address, city, region, created_at',
        [req.user.orgId, name, address, city, region ?? null]
      );
      res.status(201).json({ site: result.rows[0] });
    } catch (err) {
      next(err);
    }
  }
);

router.put(
  '/sites/:id',
  requireRole('admin', 'manager'),
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        missingUser(res);
        return;
      }
      const { name, address, city, region } = req.body as {
        name?: string;
        address?: string;
        city?: string;
        region?: string;
      };
      const sets: string[] = [];
      const params: unknown[] = [];
      if (name !== undefined) {
        if (invalidStringField(name)) {
          res.status(400).json({ error: 'Invalid value for name' });
          return;
        }
        sets.push(`name = $${params.push(name)}`);
      }
      if (address !== undefined) {
        if (invalidStringField(address)) {
          res.status(400).json({ error: 'Invalid value for address' });
          return;
        }
        sets.push(`address = $${params.push(address)}`);
      }
      if (city !== undefined) {
        if (invalidStringField(city)) {
          res.status(400).json({ error: 'Invalid value for city' });
          return;
        }
        sets.push(`city = $${params.push(city)}`);
      }
      if (region !== undefined) {
        if (region === '' || (typeof region === 'string' && region.trim() === '')) {
          sets.push(`region = $${params.push(null)}`);
        } else {
          sets.push(`region = $${params.push(region)}`);
        }
      }
      if (sets.length === 0) {
        res.status(400).json({ error: 'No fields to update' });
        return;
      }
      params.push(req.params.id, req.user.orgId);
      const result = await query<SiteRow>(
        `UPDATE customer_sites SET ${sets.join(', ')} WHERE id = $${params.length - 1} AND org_id = $${params.length} RETURNING id, org_id, name, address, city, region, created_at`,
        params
      );
      if (result.rows.length === 0) {
        res.status(404).json({ error: 'Not found' });
        return;
      }
      res.json({ site: result.rows[0] });
    } catch (err) {
      next(err);
    }
  }
);

router.delete(
  '/sites/:id',
  requireRole('admin'),
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        missingUser(res);
        return;
      }
      const { id } = req.params;
      const exists = await query<SiteRow>(
        'SELECT id FROM customer_sites WHERE id = $1 AND org_id = $2',
        [id, req.user.orgId]
      );
      if (exists.rows.length === 0) {
        res.status(404).json({ error: 'Not found' });
        return;
      }
      try {
        await query('DELETE FROM customer_sites WHERE id = $1 AND org_id = $2', [
          id,
          req.user.orgId,
        ]);
      } catch (err) {
        const code = (err as { code?: string }).code;
        if (code === '23503') {
          res.status(409).json({ error: 'Site in use' });
          return;
        }
        throw err;
      }
      res.status(204).send();
    } catch (err) {
      next(err);
    }
  }
);

export default router;
