import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '@life-agents/ui';
import { UndoSnackbar } from './UndoSnackbar';

jest.useFakeTimers();

it('offers undo and hides after the duration', () => {
  const onUndo = jest.fn();
  const onHide = jest.fn();
  render(<ThemeProvider><UndoSnackbar visible label="Eaten: milk" undoLabel="Undo" onUndo={onUndo} onHide={onHide} durationMs={5000} /></ThemeProvider>);
  fireEvent.press(screen.getByText('Undo'));
  expect(onUndo).toHaveBeenCalledTimes(1);
  act(() => jest.advanceTimersByTime(5000));
  expect(onHide).toHaveBeenCalledTimes(1);
});

it('gives a fresh five seconds to a second action with the same label', () => {
  const onHide = jest.fn();
  const first = <ThemeProvider><UndoSnackbar visible actionId="group-1" label="Eaten: milk" undoLabel="Undo" onUndo={jest.fn()} onHide={onHide} durationMs={5000} /></ThemeProvider>;
  const { rerender } = render(first);
  act(() => jest.advanceTimersByTime(4000));
  rerender(<ThemeProvider><UndoSnackbar visible actionId="group-2" label="Eaten: milk" undoLabel="Undo" onUndo={jest.fn()} onHide={onHide} durationMs={5000} /></ThemeProvider>);
  act(() => jest.advanceTimersByTime(1000));
  expect(onHide).not.toHaveBeenCalled();
  act(() => jest.advanceTimersByTime(4000));
  expect(onHide).toHaveBeenCalledTimes(1);
});
