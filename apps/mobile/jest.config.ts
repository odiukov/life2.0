import type { Config } from 'jest';

const config: Config = {
  preset: 'react-native',
  transform: {
    '^.+\\.(ts|tsx)$': [
      'ts-jest',
      {
        tsconfig: {
          jsx: 'react-jsx',
        },
      },
    ],
  },
  moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx'],
  testMatch: ['**/*.test.ts?(x)'],
  moduleNameMapper: {
    '^expo-linear-gradient$': '<rootDir>/src/__mocks__/expo-linear-gradient.tsx',
    '^expo-haptics$': '<rootDir>/src/__mocks__/expo-haptics.ts',
    '^expo-file-system/legacy$': '<rootDir>/src/__mocks__/expo-file-system.ts',
    '^expo-image-picker$': '<rootDir>/src/__mocks__/expo-image-picker.ts',
    '^@/(.*)$': '<rootDir>/src/$1',
    '^@life-agents/ui$': '<rootDir>/../../packages/ui/src/index.ts',
    '^@life-agents/i18n$': '<rootDir>/../../packages/i18n/src/index.ts',
    '^react-native-safe-area-context$':
      '<rootDir>/src/__mocks__/react-native-safe-area-context.tsx',
    '^react-native-svg$': '<rootDir>/src/__mocks__/react-native-svg.tsx',
    '^expo-router$': '<rootDir>/src/__mocks__/expo-router.tsx',
    '^react-native-url-polyfill(/.*)?$': '<rootDir>/src/__mocks__/react-native-url-polyfill.ts',
    '^expo-secure-store$': '<rootDir>/src/__mocks__/expo-secure-store.ts',
    '^expo-crypto$': '<rootDir>/src/__mocks__/expo-crypto.ts',
    '^@kingstinct/react-native-healthkit$':
      '<rootDir>/src/__mocks__/@kingstinct/react-native-healthkit.ts',
    '^@react-native-async-storage/async-storage$':
      '<rootDir>/src/__mocks__/@react-native-async-storage/async-storage.ts',
    '^expo-background-fetch$': '<rootDir>/src/__mocks__/expo-background-fetch.ts',
    '^expo-task-manager$': '<rootDir>/src/__mocks__/expo-task-manager.ts',
    '^expo-web-browser$': '<rootDir>/src/__mocks__/expo-web-browser.ts',
    '^expo-sqlite$': '<rootDir>/src/__mocks__/expo-sqlite.ts',
    '^react-native-keyboard-controller$': 'react-native-keyboard-controller/jest',
    '^expo-document-picker$': '<rootDir>/src/__mocks__/expo-document-picker.ts',
    '^expo-audio$': '<rootDir>/src/__mocks__/expo-audio.ts',
    '^expo-notifications$': '<rootDir>/src/__mocks__/expo-notifications.ts',
    '^expo-linking$': '<rootDir>/src/__mocks__/expo-linking.ts',
    '^@react-navigation/bottom-tabs$': '<rootDir>/src/__mocks__/react-navigation-bottom-tabs.ts',
    '^react-native-reanimated$': '<rootDir>/src/__mocks__/react-native-reanimated.tsx',
  },
  setupFiles: ['<rootDir>/src/jest.setup.env.ts', 'react-native-gesture-handler/jestSetup'],
  transformIgnorePatterns: [
    'node_modules/(?!((jest-)?react-native|@react-native(-community)?|expo|@expo|openapi-fetch|openapi-typescript-helpers|react-native-keyboard-controller|react-native-gesture-handler)/)',
  ],
};

export default config;
