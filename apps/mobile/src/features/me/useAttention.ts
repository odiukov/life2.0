import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { GatewaySchemas } from '@life-agents/api-client';
import { gateway } from '@/api/gateway';

export type AttentionItem = GatewaySchemas['AttentionItemOut'];
export type AttentionData = GatewaySchemas['AttentionOut'];
export const ATTENTION_KEY = ['me-attention'] as const;

export function useAttention(enabled: boolean) {
  return useQuery({
    queryKey: ATTENTION_KEY,
    enabled,
    queryFn: async (): Promise<AttentionData> => {
      const { data, error } = await gateway.GET('/me/attention');
      if (error) throw error;
      return data as AttentionData;
    },
  });
}

export function useDismissAttention() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await gateway.POST('/me/attention/{item_id}/dismiss', {
        params: { path: { item_id: id } },
      });
      if (error) throw error;
    },
    onMutate: async (id: string) => {
      await client.cancelQueries({ queryKey: ATTENTION_KEY });
      const previous = client.getQueryData<AttentionData>(ATTENTION_KEY);
      if (previous) {
        client.setQueryData<AttentionData>(ATTENTION_KEY, {
          ...previous,
          items: previous.items.filter((i) => i.id !== id),
        });
      }
      return { previous };
    },
    onError: (_error, _id, context) => {
      if (context?.previous) client.setQueryData(ATTENTION_KEY, context.previous);
    },
    onSettled: () => client.invalidateQueries({ queryKey: ATTENTION_KEY }),
  });
}
