import { feedDay, MAX_OFFSET } from './useDayFeed';

test('feedDay counts back in local days', () => {
  const today = new Date(2026, 9, 14, 0, 30); // local 14 Oct 00:30
  expect(feedDay(today, 0)).toBe('2026-10-14');
  expect(feedDay(today, 1)).toBe('2026-10-13');
  expect(feedDay(today, MAX_OFFSET)).toBe('2026-09-14');
});

import React from 'react';
import { renderHook, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { gateway } from '@/api/gateway';
import { FEED_KEY, useDayFeed } from './useDayFeed';

jest.mock('@/api/gateway', () => ({ gateway: { GET: jest.fn() } }));

test('fetches and caches independently per requested day; errors remain query errors', async () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  const get = jest.mocked(gateway.GET);
  get.mockResolvedValueOnce({ data: { date: '2026-10-14', items: [], unavailable: [] } } as never);
  get.mockResolvedValueOnce({ error: { detail: 'unavailable' } } as never);
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
  const { result, rerender, unmount } = renderHook(({ day }: { day: string }) => useDayFeed(day), {
    initialProps: { day: '2026-10-14' },
    wrapper,
  });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(get).toHaveBeenCalledWith('/me/feed', { params: { query: { date: '2026-10-14' } } });
  rerender({ day: '2026-10-13' });
  await waitFor(() => expect(result.current.isError).toBe(true));
  expect(client.getQueryData([...FEED_KEY, '2026-10-14'])).toEqual({
    date: '2026-10-14',
    items: [],
    unavailable: [],
  });
  unmount();
  client.clear();
});

test('local day arithmetic crosses month and year boundaries', () => {
  expect(feedDay(new Date(2026, 0, 1, 0, 1), 1)).toBe('2025-12-31');
  expect(feedDay(new Date(2024, 2, 1, 23, 59), 1)).toBe('2024-02-29');
});
