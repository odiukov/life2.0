import React from 'react';
import { ThemeProvider } from '@life-agents/ui';
import { fireEvent, render as baseRender, screen } from '@testing-library/react-native';
import { DayFeed } from './DayFeed';

jest.mock('@/lib/locale', () => ({ appLocale: () => 'en' }));
const feed = {
  date: '2026-10-14',
  items: [
    {
      agent: 'nutrition',
      id: 'n1',
      at: '2026-10-14T12:30:00+03:00',
      kind: 'event' as const,
      text: 'Lunch: 640 kcal, protein 32 g',
    },
    {
      agent: 'nutrition',
      id: 'n2',
      at: '2026-10-14T12:00:00+03:00',
      kind: 'insight' as const,
      text: 'Three days low on protein',
    },
  ],
  unavailable: ['sleep', 'workout'],
};

test('events, insight cards, the unavailable line, and taps open the agent', () => {
  const onOpenAgent = jest.fn();
  render(
    <DayFeed
      feed={feed}
      loading={false}
      error={false}
      onRetry={jest.fn()}
      onOpenAgent={onOpenAgent}
    />,
  );
  expect(screen.getByText('Lunch: 640 kcal, protein 32 g')).toBeTruthy();
  expect(screen.getByText('INSIGHT')).toBeTruthy();
  expect(screen.getByText(/are unavailable right now/)).toBeTruthy();
  fireEvent.press(screen.getByText('Lunch: 640 kcal, protein 32 g'));
  expect(onOpenAgent).toHaveBeenCalledWith('nutrition');
});

test('an empty day and an error', () => {
  const { rerender } = render(
    <DayFeed
      feed={{ ...feed, items: [], unavailable: [] }}
      loading={false}
      error={false}
      onRetry={jest.fn()}
      onOpenAgent={jest.fn()}
    />,
  );
  expect(screen.getByText('Quiet so far — tap the button below to log something.')).toBeTruthy();
  const onRetry = jest.fn();
  rerender(
    <DayFeed feed={undefined} loading={false} error onRetry={onRetry} onOpenAgent={jest.fn()} />,
  );
  fireEvent.press(screen.getByText('Retry'));
  expect(onRetry).toHaveBeenCalled();
});

function render(ui: React.ReactElement) {
  return baseRender(ui, { wrapper: ThemeProvider });
}
