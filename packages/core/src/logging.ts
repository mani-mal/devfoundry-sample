export interface LogEntry {
  timestamp: Date;
  level: 'debug' | 'info' | 'warn' | 'error';
  service: string;
  context: Record<string, string>;
  message: string;
  metadata?: Record<string, unknown>;
}

export interface Logger {
  debug(message: string, context?: Record<string, string>, metadata?: Record<string, unknown>): void;
  info(message: string, context?: Record<string, string>, metadata?: Record<string, unknown>): void;
  warn(message: string, context?: Record<string, string>, metadata?: Record<string, unknown>): void;
  error(message: string, context?: Record<string, string>, metadata?: Record<string, unknown>): void;
}

export class ConsoleLogger implements Logger {
  private readonly service: string;
  private readonly minLevel: 'debug' | 'info' | 'warn' | 'error';

  constructor(service: string, minLevel: 'debug' | 'info' | 'warn' | 'error' = 'info') {
    this.service = service;
    this.minLevel = minLevel;
  }

  debug(message: string, context: Record<string, string> = {}, metadata?: Record<string, unknown>): void {
    if (this.minLevel === 'debug') {
      this.log('debug', message, context, metadata);
    }
  }

  info(message: string, context: Record<string, string> = {}, metadata?: Record<string, unknown>): void {
    if (['debug', 'info'].includes(this.minLevel)) {
      this.log('info', message, context, metadata);
    }
  }

  warn(message: string, context: Record<string, string> = {}, metadata?: Record<string, unknown>): void {
    if (['debug', 'info', 'warn'].includes(this.minLevel)) {
      this.log('warn', message, context, metadata);
    }
  }

  error(message: string, context: Record<string, string> = {}, metadata?: Record<string, unknown>): void {
    this.log('error', message, context, metadata);
  }

  private log(level: 'debug' | 'info' | 'warn' | 'error', message: string, context: Record<string, string>, metadata?: Record<string, unknown>): void {
    const entry: LogEntry = {
      timestamp: new Date(),
      level,
      service: this.service,
      context: { ...context, service: this.service },
      message,
      metadata,
    };

    const formatted = this.formatEntry(entry);
    console[level](formatted);
  }

  private formatEntry(entry: LogEntry): string {
    const { timestamp, level, service, context, message, metadata } = entry;
    const contextStr = Object.entries(context)
      .map(([k, v]) => `${k}=${v}`)
      .join(' ');
    const metadataStr = metadata ? ` ${JSON.stringify(metadata)}` : '';
    return `${timestamp.toISOString()} [${level.toUpperCase()}] [${service}] [${contextStr}] ${message}${metadataStr}`;
  }
}

export const createLogger = (service: string, minLevel: 'debug' | 'info' | 'warn' | 'error' = 'info'): Logger => {
  return new ConsoleLogger(service, minLevel);
};
