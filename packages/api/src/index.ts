import express, { Request, Response } from 'express';
import { DevFoundryCore } from '@dev-foundry/core';

export class ApiServer {
  private app: express.Express;
  private core: DevFoundryCore;

  constructor(core: DevFoundryCore, port: number = 8000) {
    this.app = express();
    this.core = core;
    this.setupRoutes();
  }

  private setupRoutes(): void {
    this.app.use(express.json());
    
    this.app.get('/health', (req: Request, res: Response) => {
      res.json({ status: 'ok' });
    });
  }

  public start(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.app.listen(8000, () => {
        console.log('API server started on port 8000');
        resolve();
      });
    });
  }
}
