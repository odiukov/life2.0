import React from 'react';
import { ThemeProvider } from '@life-agents/ui';
import { fireEvent, render as baseRender, screen } from '@testing-library/react-native';
import { MetricChips } from './MetricChips';

jest.mock('@/lib/locale', () => ({ appLocale: () => 'en' }));
const summary = {
  agents: [
    {
      agent: 'sleep',
      label: 'Sleep',
      metric: '7h 40m',
      detail: null,
      tint: 'success',
      progress: 0.9,
    },
  ],
  rings: { readyPct: 82, hrvPct: 60, hrvMs: 48, stepsPct: 61, moodPct: 70 },
  alerts: [],
  unavailable: ['mood'],
};

test('rings and agent chips; unavailable is a dash; taps report the agent', () => {
  const onAgent = jest.fn();
  render(<MetricChips summary={summary as never} rows={new Map()} onAgent={onAgent} />);
  expect(screen.getByText('82%')).toBeTruthy();
  expect(screen.getByText('7h 40m')).toBeTruthy();
  expect(screen.getByTestId('chip-mood')).toHaveTextContent(/—/);
  fireEvent.press(screen.getByTestId('ring-ready'));
  expect(onAgent).toHaveBeenLastCalledWith('recovery');
  fireEvent.press(screen.getByTestId('chip-sleep'));
  expect(onAgent).toHaveBeenLastCalledWith('sleep');
});

function render(ui: React.ReactElement) {
  return baseRender(ui, { wrapper: ThemeProvider });
}

test('optional rings render dashes; setup chips show plus unless unavailable', () => {
  const rows = new Map([
    ['sleep', { status: 'needs_setup' }],
    ['mood', { status: 'needs_setup' }],
  ]);
  render(
    <MetricChips
      summary={{ agents: [], unavailable: ['mood'] }}
      rows={rows as never}
      onAgent={jest.fn()}
    />,
  );
  expect(screen.getByTestId('chip-sleep')).toHaveTextContent(/＋/);
  expect(screen.getByTestId('chip-mood')).toHaveTextContent(/—/);
  expect(screen.getByTestId('ring-ready')).toHaveTextContent(/—/);
});
