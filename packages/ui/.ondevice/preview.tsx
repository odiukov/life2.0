import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { ThemeProvider } from '../src/theme';

export const decorators = [
  (Story: React.FC) => (
    <SafeAreaProvider>
      <ThemeProvider>
        <Story />
      </ThemeProvider>
    </SafeAreaProvider>
  ),
];

export const parameters = { controls: { expanded: true } };
