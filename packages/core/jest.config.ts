import type { JestConfigWithTsJest } from 'ts-jest';

const config: JestConfigWithTsJest = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  moduleNameMapper: {
    '^@dev-foundry/core$': '<rootDir>/src',
    '^worker$': '<rootDir>/../../packages/worker/src',
    '^integrations-routeforge$': '<rootDir>/../../packages/integrations/routeforge/src',
    '^integrations-opencode$': '<rootDir>/../../packages/integrations/opencode/src',
  },
  testMatch: ['**/__tests__/**/*.test.ts'],
  transform: {
    '^.+\\.tsx?$': ['ts-jest', { useESM: false }],
  },
  modulePathIgnorePatterns: ['<rootDir>/dist', '<rootDir>/node_modules'],
  globals: {
    'ts-jest': {
      diagnostics: false,
    },
  },
};

export default config;
