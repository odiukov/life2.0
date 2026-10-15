import React from 'react';
import { ThemeProvider, type AgentId } from '@life-agents/ui';
import { fireEvent, render, screen } from '@testing-library/react-native';
import type { AgentRow } from '../agents/agentStatusRules';
import { AllAgentsGrid } from './AllAgentsGrid';
jest.mock('@/lib/locale', () => ({ appLocale: () => 'en' }));
test('grid keeps status buckets, unavailable filtering and selection', () => {
  const onPick = jest.fn();
  const row = (id: AgentId, status: AgentRow['status'], cta: AgentRow['cta']): AgentRow => ({
    id,
    status,
    cta,
    description: '',
    hint: null,
  });
  const rows = new Map<AgentId, AgentRow>([
    ['sleep', row('sleep', 'ready', null)],
    ['recovery', row('recovery', 'needs_setup', { kind: 'integrations', panel: 'garmin' })],
    ['mood', row('mood', 'needs_setup', { kind: 'chat-prefill', text: 'Log mood' })],
  ]);
  render(
    <ThemeProvider>
      <AllAgentsGrid
        summary={{ agents: [], unavailable: ['finance'] }}
        rows={rows}
        onPick={onPick}
      />
    </ThemeProvider>,
  );
  expect(screen.queryByText('Finance')).toBeNull();
  const tiles = screen.getAllByRole('button');
  fireEvent.press(tiles[0]);
  expect(onPick).toHaveBeenLastCalledWith('sleep');
  fireEvent.press(tiles[tiles.length - 1]);
  expect(onPick).toHaveBeenLastCalledWith('recovery');
  expect(screen.getByText('connect')).toBeTruthy();
  expect(screen.getByText('log')).toBeTruthy();
});
