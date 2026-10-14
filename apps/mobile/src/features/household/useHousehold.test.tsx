import React from 'react';
import { act, renderHook, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { gateway } from '@/api/gateway';
import { HOUSEHOLD_KEY, useHouseholdMutations } from './useHousehold';

jest.mock('@/api/gateway', () => ({
  gateway: {
    GET: jest.fn(),
    POST: jest.fn(async () => ({ data: { id: 'new-household' } })),
    PATCH: jest.fn(),
    DELETE: jest.fn(async () => ({ data: undefined })),
  },
}));

const clients: QueryClient[] = [];

afterEach(() => {
  clients.forEach((client) => client.clear());
  clients.length = 0;
  jest.restoreAllMocks();
});

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { gcTime: 0 } },
  });
  clients.push(client);
  const invalidated = jest.spyOn(client, 'invalidateQueries');
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, invalidated, ...renderHook(() => useHouseholdMutations(), { wrapper }) };
}

it.each(['join', 'leave'] as const)(
  '%s refreshes household and dependent kitchen/inbox data',
  async (operation) => {
    const { client, invalidated, result } = setup();
    await act(async () => {
      if (operation === 'join') await result.current.join.mutateAsync('ABCD-EF12');
      else await result.current.leave.mutateAsync();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    await waitFor(() =>
      expect(client.getQueryData(HOUSEHOLD_KEY)).toEqual({ id: 'new-household' }),
    );
    expect(invalidated).toHaveBeenCalledWith({ queryKey: ['kitchen'] });
    expect(invalidated).toHaveBeenCalledWith({ queryKey: ['inbox'] });
  },
);

it('removing a member refreshes household and dependent kitchen/inbox data', async () => {
  const { invalidated, result } = setup();
  await act(async () => {
    await result.current.remove.mutateAsync('member-id');
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  expect(gateway.DELETE).toHaveBeenCalledWith('/household/members/{user_id}', {
    params: { path: { user_id: 'member-id' } },
  });
  expect(invalidated).toHaveBeenCalledWith({ queryKey: HOUSEHOLD_KEY });
  expect(invalidated).toHaveBeenCalledWith({ queryKey: ['kitchen'] });
  expect(invalidated).toHaveBeenCalledWith({ queryKey: ['inbox'] });
});
