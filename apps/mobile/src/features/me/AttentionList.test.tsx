import React from 'react';
import { render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '@life-agents/ui';
import { AttentionList } from './AttentionList';
import type { AttentionItem } from './useAttention';

jest.mock('@/lib/locale', () => ({ appLocale: () => 'en' }));
jest.mock('react-native-gesture-handler/ReanimatedSwipeable', () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => children,
}));

const item = (id: string, text: string): AttentionItem => ({
  agent: 'sleep',
  id,
  level: 'normal',
  rank: 0,
  text,
  action: { type: 'agent' },
});
const ui = (items: AttentionItem[]) =>
  render(
    <ThemeProvider>
      <AttentionList items={items} onOpen={jest.fn()} onDismiss={jest.fn()} />
    </ThemeProvider>,
  );

test('renders nothing when empty', () => {
  expect(ui([]).toJSON()).toBeNull();
});

test('renders Now, cards and Earlier', () => {
  ui([item('a:1', 'First'), item('b:2', 'Second')]);
  expect(screen.getByText('Now')).toBeTruthy();
  expect(screen.getByText('First')).toBeTruthy();
  expect(screen.getByText('Second')).toBeTruthy();
  expect(screen.getByText('Earlier')).toBeTruthy();
});
