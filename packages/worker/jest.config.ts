import type { JestConfigWithTsJest } from 'ts-jest';

const config: JestConfigWithTsJest = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  forceExit: true,
  testMatch: ['**/__tests__/**/*.test.ts'],
  modulePathIgnorePatterns: ['<rootDir>/dist', '<rootDir>/node_modules'],
  globals: {
    'ts-jest': {
      diagnostics: false,
    },
  },
  moduleNameMapper: {
    '^@dev-foundry/core$': '<rootDir>/../../packages/core/src',
    '^@dev-foundry/integrations-routeforge$': '<rootDir>/../../packages/integrations/routeforge/src',
    '^@dev-foundry/integrations-context-forge$': '<rootDir>/../../packages/integrations/context-forge/src',
  },
};

export default config;
