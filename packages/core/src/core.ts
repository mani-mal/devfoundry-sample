import { Database } from './database';
import { ContextStore } from './context-store';
import { MemoryStore } from './memory-store';
import { SkillStore } from './skill-store';
import { ToolRegistry } from './tool-registry';

export interface CoreOptions {
  databaseUrl: string;
  routeForgeUrl: string;
  contextForgeUrl?: string;
  langfuseUrl?: string;
}

export class DevFoundryCore {
  private database: Database;
  private routeForgeUrl: string;
  private contextForgeUrl?: string;
  private langfuseUrl?: string;

  constructor(options: CoreOptions) {
    const { databaseUrl, routeForgeUrl, contextForgeUrl, langfuseUrl } = options;
    this.routeForgeUrl = routeForgeUrl;
    this.contextForgeUrl = contextForgeUrl;
    this.langfuseUrl = langfuseUrl;

    this.database = this.parseDatabaseUrl(databaseUrl);
  }

  private parseDatabaseUrl(url: string): Database {
    const match = url.match(/postgres(?:ql)?:\/\/([^:]+):([^@]+)@([^:]+):(\d+)\/(.+)/);
    if (!match) {
      throw new Error('Invalid database URL');
    }
    const [, username, password, host, port, database] = match;
    return new Database({
      host,
      port: parseInt(port, 10),
      database,
      username,
      password,
    });
  }

  async connect(): Promise<void> {
    await this.database.connect();
  }

  async disconnect(): Promise<void> {
    await this.database.close();
  }

  getDatabase(): Database {
    return this.database;
  }

  getRouteForgeUrl(): string {
    return this.routeForgeUrl;
  }

  getContextForgeUrl(): string | undefined {
    return this.contextForgeUrl;
  }

  getLangfuseUrl(): string | undefined {
    return this.langfuseUrl;
  }

  getContextStore(): ContextStore {
    return new ContextStore(this.database);
  }

  getMemoryStore(): MemoryStore {
    return new MemoryStore(this.database);
  }

  getSkillStore(): SkillStore {
    return new SkillStore(this.database);
  }

  getToolRegistry(): ToolRegistry {
    return new ToolRegistry(this.database);
  }
}
