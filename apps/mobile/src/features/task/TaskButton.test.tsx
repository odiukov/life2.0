import { ThemeProvider } from '@life-agents/ui';
import React from 'react';
import { act, render, screen } from '@testing-library/react-native';
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

let mockVoiceOpts: {
  onTranscript: (text: string, seconds: number) => void;
  onNotice: (text: string) => void;
  onFinished: () => void;
};
const mockVoice = {
  state: 'idle',
  seconds: 6,
  level: 0.4,
  start: jest.fn(async () => undefined),
  stop: jest.fn(async () => undefined),
  cancel: jest.fn(async () => undefined),
};
jest.mock('@/features/voice/useVoiceInput', () => ({
  useVoiceInput: (opts: typeof mockVoiceOpts) => {
    mockVoiceOpts = opts;
    return mockVoice;
  },
}));

const hold = (dx: number) =>
  act(() =>
    fireGestureHandler(getByGestureTestId('task-button-hold'), [
      { state: State.BEGAN, translationX: 0 },
      { state: State.ACTIVE, translationX: 0 },
      { state: State.ACTIVE, translationX: dx },
      { state: State.END, translationX: dx },
    ]),
  );

beforeEach(() => {
  jest.clearAllMocks();
  mockVoice.state = 'idle';
});

test('hold records and release waits for transcript with captured duration', () => {
  render(
    <ThemeProvider>
      <TaskButton />
    </ThemeProvider>,
  );
  hold(-80);
  expect(mockVoice.start).toHaveBeenCalledTimes(1);
  expect(mockVoice.stop).toHaveBeenCalledTimes(1);
  expect(mockVoice.cancel).not.toHaveBeenCalled();
  expect(useTaskSheet.getState().visible).toBe(false);
  act(() => mockVoiceOpts.onTranscript('meal', 6));
  expect(useTaskSheet.getState()).toMatchObject({
    visible: true,
    pending: { voice: { text: 'meal', seconds: 6 } },
  });
});

test('left beyond 80 points cancels and opens nothing', () => {
  render(
    <ThemeProvider>
      <TaskButton />
    </ThemeProvider>,
  );
  hold(-81);
  expect(mockVoice.cancel).toHaveBeenCalledTimes(1);
  expect(mockVoice.stop).not.toHaveBeenCalled();
  expect(haptic).toHaveBeenCalledWith('warning');
  expect(useTaskSheet.getState().visible).toBe(false);
});

test('auto completion clears hold and later release cannot stop twice', () => {
  render(
    <ThemeProvider>
      <TaskButton />
    </ThemeProvider>,
  );
  const gesture = getByGestureTestId('task-button-hold');
  act(() => gesture.handlers.onStart?.({} as never));
  act(() => mockVoiceOpts.onFinished());
  expect(screen.queryByTestId('voice-hold')).toBeNull();
  act(() => gesture.handlers.onEnd?.({ translationX: 0 } as never, true));
  expect(mockVoice.stop).not.toHaveBeenCalled();
});

test('voice failure shows notice without opening sheet', () => {
  render(
    <ThemeProvider>
      <TaskButton />
    </ThemeProvider>,
  );
  act(() => {
    mockVoiceOpts.onNotice('No audio');
    mockVoiceOpts.onFinished();
  });
  expect(screen.getByText('No audio')).toBeTruthy();
  expect(useTaskSheet.getState().visible).toBe(false);
});

// This test file loads TaskButton first, as the tab bar does on a fresh module graph.
import { VoiceHold } from './VoiceHold';
import { StyleSheet, View } from 'react-native';
test('TaskButton-first initialization leaves hold geometry finite and 64-point based', () => {
  const result = render(
    <ThemeProvider>
      <VoiceHold seconds={1} level={0.5} armed={false} transcribing={false} />
    </ThemeProvider>,
  );
  const styles = result
    .UNSAFE_getAllByType(View)
    .map((view) => StyleSheet.flatten(view.props.style));
  const rings = styles.filter((style) => style?.position === 'absolute' && 'width' in style);
  expect(rings.length).toBeGreaterThanOrEqual(3);
  for (const style of rings) {
    expect(style.width).toBe(64);
    expect(style.height).toBe(64);
    if ('borderRadius' in style) expect(style.borderRadius).toBe(32);
    if ('bottom' in style) expect(Number.isFinite(style.bottom)).toBe(true);
  }
  expect(StyleSheet.flatten(screen.getByTestId('voice-hold').props.style).bottom).toBe(88);
});
