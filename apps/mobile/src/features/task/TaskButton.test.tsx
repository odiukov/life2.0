import { ThemeProvider } from '@life-agents/ui';
import React from 'react';
import { render, screen } from '@testing-library/react-native';
import { State } from 'react-native-gesture-handler';
import { fireGestureHandler, getByGestureTestId } from 'react-native-gesture-handler/jest-utils';
import { haptic } from '@/lib/haptics';
import { TaskButton } from './TaskButton';
import { useTaskSheet } from './sheetStore';

jest.mock('@/lib/locale', () => ({ appLocale: () => 'en' }));
jest.mock('@/lib/haptics', () => ({ haptic: jest.fn() }));

beforeEach(() => useTaskSheet.setState({ visible: false, origin: null, pending: null }));

test('a tap gives light feedback and opens the sheet', () => {
  render(
    <ThemeProvider>
      <TaskButton />
    </ThemeProvider>,
  );
  fireGestureHandler(getByGestureTestId('task-button-tap'), [
    { state: State.BEGAN },
    { state: State.ACTIVE },
    { state: State.END },
  ]);
  expect(haptic).toHaveBeenCalledWith('light');
  expect(useTaskSheet.getState().visible).toBe(true);
  expect(screen.getByLabelText('New task')).toBeTruthy();
});

test('assistive activation opens the sheet with the same tap action', () => {
  render(
    <ThemeProvider>
      <TaskButton />
    </ThemeProvider>,
  );
  const button = screen.getByLabelText('New task');
  button.props.onAccessibilityTap();
  expect(useTaskSheet.getState().visible).toBe(true);
  expect(button.props.accessibilityHint).toBe('Tap to write, hold to talk');
});
