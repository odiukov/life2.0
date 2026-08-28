import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { ThemeProvider } from '@life-agents/ui';
import { YazioPanel } from './YazioPanel';

// expo-secure-store and supabase are globally mocked via jest.config moduleNameMapper.
jest.mock('@/api/client', () => ({ apiBaseUrl: 'http://test' }));
jest.mock('@/features/auth/getAuthHeaders', () => ({
  getAuthHeaders: async () => ({}),
}));

function wrap(ui: React.ReactElement) {
  return render(<ThemeProvider>{ui}</ThemeProvider>);
}

beforeEach(() => {
  (global.fetch as jest.Mock | undefined) = undefined;
});

test('shows banner when preflight returns detected: true', async () => {
  global.fetch = jest.fn(async () => ({
    ok: true,
    json: async () => ({
      detected: true,
      sample_count: 5,
      last_seen: new Date().toISOString(),
    }),
  })) as unknown as typeof fetch;

  wrap(<YazioPanel />);

  await waitFor(() => {
    expect(screen.getByTestId('yazio-preflight-banner')).toBeOnTheScreen();
  });
});

test('hides banner when preflight returns detected: false', async () => {
  global.fetch = jest.fn(async () => ({
    ok: true,
    json: async () => ({ detected: false, sample_count: 0, last_seen: null }),
  })) as unknown as typeof fetch;

  wrap(<YazioPanel />);

  await waitFor(() => expect(global.fetch).toHaveBeenCalled());
  expect(screen.queryByTestId('yazio-preflight-banner')).toBeNull();
});

test('forwards scroll events for sheet swipe coordination', () => {
  const onScroll = jest.fn();
  wrap(<YazioPanel onScroll={onScroll} />);

  fireEvent.scroll(screen.getByTestId('yazio-scroll'), {
    nativeEvent: { contentOffset: { y: 80 } },
  });

  expect(onScroll).toHaveBeenCalled();
});
