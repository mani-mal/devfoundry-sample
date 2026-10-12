import { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';
import bcrypt from 'bcryptjs';

export interface AuthUser {
  userId: string;
  orgId: string;
  role: 'admin' | 'manager' | 'technician';
  email: string;
}

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace Express {
    interface Request {
      user?: AuthUser;
    }
  }
}

const JWT_SECRET = process.env.JWT_SECRET || 'equipflow-dev-secret';

export function hashPassword(p: string): string {
  return bcrypt.hashSync(p, 10);
}

export function verifyPassword(p: string, hash: string): boolean {
  return bcrypt.compareSync(p, hash);
}

export function signToken(user: AuthUser): string {
  return jwt.sign(
    { userId: user.userId, orgId: user.orgId, role: user.role, email: user.email },
    JWT_SECRET,
    { expiresIn: '12h' }
  );
}

export function authMiddleware(req: Request, res: Response, next: NextFunction): void {
  const header = req.headers.authorization;
  if (!header || !header.startsWith('Bearer ')) {
    res.status(401).json({ error: 'Unauthorized' });
    return;
  }
  const token = header.slice('Bearer '.length).trim();
  try {
    const payload = jwt.verify(token, JWT_SECRET) as AuthUser;
    if (!payload || !payload.userId || !payload.orgId) {
      res.status(401).json({ error: 'Unauthorized' });
      return;
    }
    req.user = {
      userId: payload.userId,
      orgId: payload.orgId,
      role: payload.role,
      email: payload.email,
    };
    next();
  } catch {
    res.status(401).json({ error: 'Unauthorized' });
  }
}

export function requireRole(...roles: AuthUser['role'][]) {
  return (req: Request, res: Response, next: NextFunction): void => {
    if (!req.user || !roles.includes(req.user.role)) {
      res.status(403).json({ error: 'Forbidden' });
      return;
    }
    next();
  };
}
