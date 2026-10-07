import express, { Application, Request, Response } from 'express';
import { DevFoundryCore } from '@dev-foundry/core';

export interface ApiOptions {
  port: number;
  core: DevFoundryCore;
}

export class DevFoundryApi {
  private app: Application;
  private port: number;
  private core: DevFoundryCore;

  constructor(options: ApiOptions) {
    this.port = options.port;
    this.core = options.core;
    this.app = express();
    this.configureMiddleware();
    this.configureRoutes();
  }

  private configureMiddleware(): void {
    this.app.use(express.json());
    this.app.use(express.urlencoded({ extended: true }));
    this.app.use((req: Request, res: Response, next) => {
      res.setHeader('Content-Type', 'application/json');
      next();
    });
  }

  private configureRoutes(): void {
    this.app.get('/health', (req: Request, res: Response) => {
      res.json({ status: 'healthy', timestamp: new Date().toISOString() });
    });

    this.app.get('/api/v1/tasks', (req: Request, res: Response) => {
      res.json({ message: 'List tasks endpoint' });
    });

    this.app.post('/api/v1/tasks', (req: Request, res: Response) => {
      res.json({ message: 'Create task endpoint' });
    });

    this.app.get('/api/v1/tasks/:taskId', (req: Request, res: Response) => {
      res.json({ message: 'Get task endpoint' });
    });

    this.app.patch('/api/v1/tasks/:taskId', (req: Request, res: Response) => {
      res.json({ message: 'Update task endpoint' });
    });

    this.app.delete('/api/v1/tasks/:taskId', (req: Request, res: Response) => {
      res.json({ message: 'Cancel task endpoint' });
    });

    this.app.get('/api/v1/skills', (req: Request, res: Response) => {
      res.json({ message: 'List skills endpoint' });
    });

    this.app.post('/api/v1/skills', (req: Request, res: Response) => {
      res.json({ message: 'Create skill endpoint' });
    });

    this.app.get('/api/v1/skills/:skillId', (req: Request, res: Response) => {
      res.json({ message: 'Get skill endpoint' });
    });

    this.app.get('/api/v1/context', (req: Request, res: Response) => {
      res.json({ message: 'List context endpoint' });
    });

    this.app.post('/api/v1/context', (req: Request, res: Response) => {
      res.json({ message: 'Create context endpoint' });
    });
  }

  public start(): void {
    this.app.listen(this.port, () => {
      console.log(`DevFoundry API listening on port ${this.port}`);
    });
  }

  public getApp(): Application {
    return this.app;
  }
}
