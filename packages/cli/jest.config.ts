import type { JestConfigWithTsJest } from 'ts-jest';

const config: JestConfigWithTsJest = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  moduleNameMapper: {
    '^@dev-foundry/core$': '<rootDir>/../../core/src',
    '^@dev-foundry/integrations-context-forge$': '<rootDir>/../../integrations/context-forge/src',
  },
  testMatch: ['**/__tests__/**/*.test.ts'],
};

export default config;
