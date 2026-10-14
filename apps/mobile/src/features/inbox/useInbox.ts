import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { gateway } from '@/api/gateway';
import { useSession } from '@/features/auth/useSession';

export const INBOX_KEY = ['inbox'] as const;

export function useInbox() {
  const userId = useSession((state) => state.session?.user.id);
  return useQuery({
    queryKey: [...INBOX_KEY, userId],
    enabled: Boolean(userId),
    queryFn: async () => {
      const { data, error } = await gateway.GET('/notifications', { params: { query: { limit: 50 } } });
      if (error !== undefined || !data) throw error ?? new Error('inbox');
      return data;
    },
    refetchInterval: 60_000,
  });
}

function requireSuccess(response: { error?: unknown }): void {
  if (response.error !== undefined) throw response.error;
}

export function useInboxActions() {
  const client = useQueryClient();
  const refresh = () => { void client.invalidateQueries({ queryKey: INBOX_KEY }); };
  return {
    read: useMutation({
      mutationFn: async (id: string) => {
        requireSuccess(await gateway.POST('/notifications/{notification_id}/read', {
          params: { path: { notification_id: id } },
        }));
      },
      onSettled: refresh,
    }),
    readAll: useMutation({
      mutationFn: async () => {
        requireSuccess(await gateway.POST('/notifications/read-all'));
      },
      onSettled: refresh,
    }),
  };
}
