import { useQuery } from '@tanstack/react-query';
import { gateway } from '@/api/gateway';

export function useHaStatus() {
  return useQuery({
    queryKey: ['integrations', 'ha', 'status'],
    queryFn: async () => {
      const { data, error } = await gateway.GET('/integrations/ha/status');
      if (error || !data) throw new Error('ha_status_failed');
      return data;
    },
  });
}
