import { DevFoundryApi } from './api';

const API_PORT = process.env.API_PORT ? parseInt(process.env.API_PORT, 10) : 3000;

const coreOptions = {
  databaseUrl: process.env.DATABASE_URL || 'postgres://devfoundry:devfoundry@localhost:5432/devfoundry',
  routeForgeUrl: process.env.ROUTEFORGE_URL || 'http://localhost:8000',
};

const apiOptions = {
  port: API_PORT,
  core: undefined as any,
};

const api = new DevFoundryApi(apiOptions);
api.start();
