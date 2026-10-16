import React from 'react';
import { render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '@life-agents/ui';
import { TaskTabBar } from './TaskTabBar';

jest.mock('./TaskButton', () => {
  const { View } = jest.requireActual('react-native');
  return { TaskButton: () => <View testID="task-button" /> };
});
jest.mock('@/lib/locale', () => ({ appLocale: () => 'en' }));

test('the bar holds only the task button', () => {
  render(
    <ThemeProvider>
      <TaskTabBar {...({ state: { routes: [], index: 0 }, navigation: {} } as unknown as React.ComponentProps<typeof TaskTabBar>)} />
    </ThemeProvider>,
  );
  expect(screen.getByTestId('task-button')).toBeTruthy();
  expect(screen.queryByTestId('tab-index')).toBeNull();
  expect(screen.queryByTestId('tab-house')).toBeNull();
});
