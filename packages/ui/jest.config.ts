import type { Config } from 'jest';

const config: Config = {
  preset: 'react-native',
  transform: {
    '^.+\\.(ts|tsx)$': ['ts-jest', { tsconfig: 'tsconfig.json' }],
  },
  moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx'],
  testMatch: ['**/*.test.ts?(x)'],
  moduleNameMapper: {
    '^react-native-safe-area-context$':
      '<rootDir>/src/__mocks__/react-native-safe-area-context.tsx',
    '^react-native-svg$':
      '<rootDir>/src/__mocks__/react-native-svg.tsx',
  },
};

export default config;
