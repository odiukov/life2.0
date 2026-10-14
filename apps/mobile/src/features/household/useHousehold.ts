import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { GatewaySchemas } from '@life-agents/api-client';
import { gateway } from '@/api/gateway';

export const HOUSEHOLD_KEY = ['household'] as const;
export type Household = GatewaySchemas['HouseholdOut'];

async function unwrap<T>(promise: Promise<{ data?: T; error?: unknown }>): Promise<T> {
  const { data, error } = await promise;
  if (error !== undefined) throw error;
  return data as T;
}

export function useHousehold() {
  return useQuery({
    queryKey: HOUSEHOLD_KEY,
    queryFn: () => unwrap(gateway.GET('/household')),
  });
}

export function useHouseholdMutations() {
  const client = useQueryClient();
  const refreshHousehold = (data: Household) => client.setQueryData(HOUSEHOLD_KEY, data);
  const refreshDependents = () => {
    void client.invalidateQueries({ queryKey: ['kitchen'] });
    void client.invalidateQueries({ queryKey: ['inbox'] });
  };

  return {
    invite: useMutation({
      mutationFn: () => unwrap(gateway.POST('/household/invites')),
    }),
    preview: useMutation({
      mutationFn: (code: string) =>
        unwrap(gateway.POST('/household/join/preview', { body: { code } })),
    }),
    join: useMutation({
      mutationFn: (code: string) => unwrap(gateway.POST('/household/join', { body: { code } })),
      onSuccess: (data) => {
        refreshHousehold(data);
        refreshDependents();
      },
    }),
    leave: useMutation({
      mutationFn: () => unwrap(gateway.POST('/household/leave')),
      onSuccess: (data) => {
        refreshHousehold(data);
        refreshDependents();
      },
    }),
    update: useMutation({
      mutationFn: (body: { name?: string; digest_time?: string; timezone?: string }) =>
        unwrap(gateway.PATCH('/household', { body })),
      onSuccess: refreshHousehold,
    }),
    remove: useMutation({
      mutationFn: (memberId: string) =>
        unwrap(
          gateway.DELETE('/household/members/{user_id}', {
            params: { path: { user_id: memberId } },
          }),
        ),
      onSuccess: () => {
        void client.invalidateQueries({ queryKey: HOUSEHOLD_KEY });
        refreshDependents();
      },
    }),
  };
}
