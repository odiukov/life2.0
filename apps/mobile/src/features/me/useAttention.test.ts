import React from 'react';
import { act, renderHook, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { errorCode, gateway } from '@/api/gateway';
import { ATTENTION_KEY, useDismissAttention, type AttentionData } from './useAttention';

jest.mock('@/api/gateway', () => ({
  gateway: { GET: jest.fn(), POST: jest.fn() },
  errorCode: jest.requireActual('@/api/gateway').errorCode,
}));

const mk = (id: string) => ({
  agent: 'sleep',
  id,
  level: 'high' as const,
  rank: 0,
  text: id,
  action: { type: 'agent' as const },
});
const seed: AttentionData = { items: [mk('a:x:1'), mk('b:y:2')], unavailable: [] };

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  client.setQueryData(ATTENTION_KEY, seed);
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
  return { client, ...renderHook(() => useDismissAttention(), { wrapper }) };
}

test('removes the item optimistically before the POST resolves', async () => {
  let resolve!: (v: unknown) => void;
  jest.mocked(gateway.POST).mockReturnValue(new Promise((r) => (resolve = r)) as never);
  const { client, result } = setup();
  act(() => result.current.mutate('a:x:1'));
  await waitFor(() =>
    expect(client.getQueryData<AttentionData>(ATTENTION_KEY)?.items.map((i) => i.id)).toEqual([
      'b:y:2',
    ]),
  );
  expect(gateway.POST).toHaveBeenCalledWith('/me/attention/{item_id}/dismiss', {
    params: { path: { item_id: 'a:x:1' } },
  });
  await act(async () => resolve({}));
});

test('rolls back on error and exposes the error code', async () => {
  jest.mocked(gateway.POST).mockResolvedValue({ error: { detail: 'agent_unavailable' } } as never);
  const { client, result } = setup();
  act(() => result.current.mutate('a:x:1'));
  await waitFor(() => expect(result.current.isError).toBe(true));
  expect(errorCode(result.current.error)).toBe('agent_unavailable');
  expect(client.getQueryData<AttentionData>(ATTENTION_KEY)?.items).toHaveLength(2);
});
