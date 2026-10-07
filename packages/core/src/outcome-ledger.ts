import { Task, TaskPhase, TaskOutcome, EvidenceItem, TraceReference } from '@dev-foundry/core';
import { Pool, Client } from 'pg';
import { v4 as uuidv4 } from 'uuid';
import { createLogger } from '@dev-foundry/core';
import * as path from 'path';
import * as fs from 'fs/promises';

export interface OutcomeLedgerConfig {
  databaseUrl: string;
  langfuseUrl?: string;
}
