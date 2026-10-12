import { Router, Request, Response, NextFunction } from 'express';
import { query } from '../db';
import { authMiddleware, requireRole, hashPassword } from '../auth';

const router = Router();

interface UserRow {
  id: string;
  org_id: string;
  email: string;
  name: string;
  role: 'admin' | 'manager' | 'technician';
  created_at: Date;
}

const VALID_ROLES = ['admin', 'manager', 'technician'];

router.use(authMiddleware);

router.get(
  '/users',
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        res.status(401).json({ error: 'Unauthorized' });
        return;
      }
      const result = await query<UserRow>(
        'SELECT id, org_id, email, name, role, created_at FROM users WHERE org_id = $1 ORDER BY created_at ASC',
        [req.user.orgId]
      );
      res.json({ users: result.rows });
    } catch (err) {
      next(err);
    }
  }
);

router.post(
  '/users',
  requireRole('admin', 'manager'),
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        res.status(401).json({ error: 'Unauthorized' });
        return;
      }
      const { email, name, role, password } = req.body as {
        email?: string;
        name?: string;
        role?: string;
        password?: string;
      };
      if (!email || !name || !password) {
        res.status(400).json({ error: 'Missing required fields' });
        return;
      }
      if (!role || !VALID_ROLES.includes(role)) {
        res.status(400).json({ error: 'Invalid role' });
        return;
      }
      const passwordHash = hashPassword(password);
      const result = await query<UserRow>(
        'INSERT INTO users (org_id, email, name, role, password_hash) VALUES ($1, $2, $3, $4, $5) RETURNING id, org_id, email, name, role, created_at',
        [req.user.orgId, email, name, role, passwordHash]
      );
      const user = result.rows[0];
      res.status(201).json({
        user: { id: user.id, email: user.email, name: user.name, role: user.role },
      });
    } catch (err) {
      next(err);
    }
  }
);

router.delete(
  '/users/:id',
  requireRole('admin'),
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user) {
        res.status(401).json({ error: 'Unauthorized' });
        return;
      }
      const { id } = req.params;
      const result = await query(
        'DELETE FROM users WHERE id = $1 AND org_id = $2',
        [id, req.user.orgId]
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
