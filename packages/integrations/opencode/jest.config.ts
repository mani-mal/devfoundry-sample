import type { JestConfigWithTsJest } from 'ts-jest';

const config: JestConfigWithTsJest = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  testMatch: ['**/__tests__/**/*.test.ts'],
  modulePathIgnorePatterns: ['<rootDir>/dist', '<rootDir>/node_modules'],
  globals: {
    'ts-jest': {
      diagnostics: false,
    },
  },
};

export default config;
