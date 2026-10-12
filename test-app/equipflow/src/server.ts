import express, { Request, Response, NextFunction } from 'express';
import orgsRouter from './routes/orgs';
import usersRouter from './routes/users';
import sitesRouter from './routes/sites';
import equipmentRouter from './routes/equipment';
import requestsRouter from './routes/requests';
import workordersRouter from './routes/workorders';

const app = express();
app.use(express.json());

app.get('/health', (_req: Request, res: Response) => {
  res.json({ status: 'ok' });
});

app.use(orgsRouter);
app.use(usersRouter);
app.use(sitesRouter);
app.use(equipmentRouter);
app.use(requestsRouter);
app.use(workordersRouter);

interface PgError extends Error {
  code?: string;
}

app.use((err: PgError, _req: Request, res: Response, _next: NextFunction) => {
  if (err && err.code === '23505') {
    res.status(409).json({ error: 'Already exists' });
    return;
  }
  if (err && err.code === '22P02') {
    res.status(404).json({ error: 'Not found' });
    return;
  }
  if (err && err.code === '23503') {
    res.status(404).json({ error: 'Not found' });
    return;
  }
  if (err && err.code === '23514') {
    res.status(400).json({ error: 'Invalid role' });
    return;
  }
  res.status(500).json({ error: 'Internal server error' });
});

const PORT = process.env.PORT || 4600;

export default app;

if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`equipflow listening on port ${PORT}`);
  });
}
