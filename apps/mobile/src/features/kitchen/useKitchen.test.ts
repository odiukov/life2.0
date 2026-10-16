import React from 'react';
import { act, renderHook } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { gateway } from '@/api/gateway';
import { ATTENTION_KEY } from '../me/useAttention';
import { KITCHEN_KEY, useKitchenActions } from './useKitchen';

jest.mock('@/api/gateway', () => ({
  gateway: { GET: jest.fn(), POST: jest.fn() },
  errorCode: jest.requireActual('@/api/gateway').errorCode,
}));

function setup() {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const invalidate = jest.spyOn(client, 'invalidateQueries');
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
  return { invalidate, ...renderHook(() => useKitchenActions(), { wrapper }) };
}
const keys = (spy: jest.SpyInstance) => spy.mock.calls.map(([filters]) => filters?.queryKey);

test.each([
  ['succeeds', { data: {} }],
  ['fails', { error: { detail: 'boom' } }],
])('an item action that %s refreshes kitchen and attention', async (_name, reply) => {
  jest.mocked(gateway.POST).mockResolvedValue(reply as never);
  const { invalidate, result } = setup();
  await act(async () => {
    await result.current.act
      .mutateAsync({ id: 'i1', body: { action: 'used' } as never })
      .catch(() => {});
  });
  expect(keys(invalidate)).toEqual(expect.arrayContaining([KITCHEN_KEY, ATTENTION_KEY]));
});

test('undo refreshes kitchen and attention', async () => {
  jest.mocked(gateway.POST).mockResolvedValue({ data: {} } as never);
  const { invalidate, result } = setup();
  await act(async () => {
    await result.current.undo.mutateAsync('g1');
  });
  expect(keys(invalidate)).toEqual(expect.arrayContaining([KITCHEN_KEY, ATTENTION_KEY]));
});
