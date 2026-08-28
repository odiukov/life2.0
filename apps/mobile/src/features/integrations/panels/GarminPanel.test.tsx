import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { ThemeProvider } from '@life-agents/ui';
import { GarminPanel } from './GarminPanel';

// expo-secure-store and supabase are globally mocked via jest.config moduleNameMapper.
// We mock the api-client module to avoid pulling its mock-fetch / openapi-fetch chain.
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
      sample_count: 12,
      last_seen: new Date().toISOString(),
    }),
  })) as unknown as typeof fetch;

  wrap(<GarminPanel />);

  await waitFor(() => {
    expect(screen.getByTestId('garmin-preflight-banner')).toBeOnTheScreen();
  });
});

test('hides banner when preflight returns detected: false', async () => {
  global.fetch = jest.fn(async () => ({
    ok: true,
    json: async () => ({ detected: false, sample_count: 0, last_seen: null }),
  })) as unknown as typeof fetch;

  wrap(<GarminPanel />);

  await waitFor(() => expect(global.fetch).toHaveBeenCalled());
  expect(screen.queryByTestId('garmin-preflight-banner')).toBeNull();
});

test('forwards scroll events for sheet swipe coordination', () => {
  const onScroll = jest.fn();
  wrap(<GarminPanel onScroll={onScroll} />);

  fireEvent.scroll(screen.getByTestId('garmin-scroll'), {
    nativeEvent: { contentOffset: { y: 80 } },
  });

  expect(onScroll).toHaveBeenCalled();
});
