import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { GatewaySchemas } from '@life-agents/api-client';
import { gateway } from '@/api/gateway';
import { ATTENTION_KEY } from '../me/useAttention';

export type KitchenItem = GatewaySchemas['KitchenItem'];
export type Location = 'fridge' | 'freezer' | 'pantry';
export type ItemAction = GatewaySchemas['ItemActionIn'];
export const KITCHEN_KEY = ['kitchen'] as const;

async function unwrap<T>(promise: Promise<{ data?: T; error?: unknown }>): Promise<T> {
  const { data, error } = await promise;
  if (error !== undefined) throw error;
  return data as T;
}

export function useInventory(location: Location, householdId?: string) {
  return useQuery({
    queryKey: [...KITCHEN_KEY, householdId, 'inventory', location],
    enabled: Boolean(householdId),
    queryFn: () => unwrap(gateway.GET('/kitchen/inventory', { params: { query: { location } } })),
  });
}

export function useKitchenActions() {
  const client = useQueryClient();
  // Kitchen items feed the Me attention cards too, so acting on one must clear its card.
  const refresh = () =>
    Promise.all([
      client.invalidateQueries({ queryKey: KITCHEN_KEY }),
      client.invalidateQueries({ queryKey: ATTENTION_KEY }),
    ]);
  return {
    act: useMutation({
      mutationFn: ({ id, body }: { id: string; body: ItemAction }) =>
        unwrap(gateway.POST('/kitchen/items/{item_id}/action', { params: { path: { item_id: id } }, body })),
      onSettled: refresh,
    }),
    undo: useMutation({
      mutationFn: (groupId: string) =>
        unwrap(gateway.POST('/kitchen/undo/{group_id}', { params: { path: { group_id: groupId } } })),
      onSettled: refresh,
    }),
  };
}
