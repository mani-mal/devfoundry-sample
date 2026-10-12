import { Router, Request, Response, NextFunction } from 'express';
import { query } from '../db';
import { authMiddleware, verifyToken, hashPassword, signToken } from '../auth';

const SLUG_PATTERN = /^[a-z0-9](-?[a-z0-9])*$/;

const router = Router();

interface OrgRow {
  id: string;
  name: string;
  slug: string;
  created_at: Date;
}

interface UserRow {
  id: string;
  org_id: string;
  email: string;
  name: string;
  role: 'admin' | 'manager' | 'technician';
  password_hash: string;
}

router.post(
  '/orgs',
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      const { name, slug, adminEmail, adminName, adminPassword } = req.body as {
        name?: string;
        slug?: string;
        adminEmail?: string;
        adminName?: string;
        adminPassword?: string;
      };
      if (!name || !slug || !adminEmail || !adminName || !adminPassword) {
        res.status(400).json({ error: 'Missing required fields' });
        return;
      }
      const orgExists = await query<{ id: string }>(
        'SELECT 1 FROM orgs WHERE LOWER(slug) = LOWER($1)',
        [slug]
      );
      if (orgExists.rows.length > 0) {
        res.status(409).json({ error: 'Slug already exists' });
        return;
      }
      if (typeof slug !== 'string' || slug.length < 2 || slug.length > 63 || !SLUG_PATTERN.test(slug)) {
        res.status(400).json({ error: 'Invalid slug format' });
        return;
      }
      if (verifyToken(req.headers.authorization)) {
        res.status(403).json({ error: 'Sign out to create a new organization' });
        return;
      }
      const emailExists = await query<{ id: string }>(
        'SELECT 1 FROM users WHERE LOWER(email) = LOWER($1)',
        [adminEmail]
      );
      if (emailExists.rows.length > 0) {
        res.status(409).json({ error: 'Already exists' });
        return;
      }
      const passwordHash = hashPassword(adminPassword);
      await query('BEGIN');
      try {
        const orgResult = await query<OrgRow>(
          'INSERT INTO orgs (name, slug) VALUES ($1, $2) RETURNING id, name, slug',
          [name, slug]
        );
        const org = orgResult.rows[0];
        const userResult = await query<UserRow>(
          'INSERT INTO users (org_id, email, name, role, password_hash) VALUES ($1, $2, $3, $4, $5) RETURNING id, email, role',
          [org.id, adminEmail, adminName, 'admin', passwordHash]
        );
        const admin = userResult.rows[0];
        await query('COMMIT');
        const token = signToken({
          userId: admin.id,
          orgId: org.id,
          role: 'admin',
          email: admin.email,
        });
        res.status(201).json({
          org: { id: org.id, name: org.name, slug: org.slug },
          admin: { id: admin.id, email: admin.email, role: admin.role },
          token,
        });
      } catch (err) {
        await query('ROLLBACK').catch(() => undefined);
        throw err;
      }
    } catch (err) {
      next(err);
    }
  }
);

router.get(
  '/orgs',
  authMiddleware,
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      if (!req.user || req.user.role !== 'admin') {
        res.status(403).json({ error: 'Forbidden' });
        return;
      }
      const result = await query<OrgRow>(
        'SELECT id, name, slug, created_at FROM orgs ORDER BY created_at ASC'
      );
      res.json({ orgs: result.rows });
    } catch (err) {
      next(err);
    }
  }
);

router.get(
  '/orgs/:id',
  authMiddleware,
  async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    try {
      const { id } = req.params;
      if (!req.user) {
        res.status(401).json({ error: 'Unauthorized' });
        return;
      }
      if (req.user.role !== 'admin' && id !== req.user.orgId) {
        res.status(404).json({ error: 'Not found' });
        return;
      }
      const result = await query<OrgRow>(
        'SELECT id, name, slug, created_at FROM orgs WHERE id = $1',
        [id]
      );
      if (result.rows.length === 0) {
        res.status(404).json({ error: 'Not found' });
        return;
      }
      res.json({ org: result.rows[0] });
    } catch (err) {
      next(err);
    }
  }
);

export default router;
