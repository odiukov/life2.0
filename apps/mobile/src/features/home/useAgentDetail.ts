import { useQuery } from '@tanstack/react-query';
import type { AgentId } from '@life-agents/ui';
import { api } from '@/api/client';
import type { paths } from '@life-agents/api-client';

type BackendAgentId = paths['/agents/{agent_id}/detail']['get']['parameters']['path']['agent_id'];

// Mirrors orchestrator/app/agent_detail.py:VALID_AGENT_IDS — agents without a
// backend detail builder skip the request to avoid a 404.
const BACKEND_DETAIL_AGENTS: ReadonlySet<AgentId> = new Set<AgentId>([
  'sleep',
  'workout',
  'nutrition',
  'mood',
  'habits',
  'recovery',
  'medication',
  'finance',
  'calendar',
]);

export const hasAgentDetail = (agentId: AgentId | null): boolean =>
  agentId !== null && BACKEND_DETAIL_AGENTS.has(agentId);

export type HistoryPoint = {
  date: string;
  value: number;
  label: string;
};

export type AgentDetail = {
  agent: AgentId;
  insight: string;
  metrics: Record<string, unknown>;
  history: HistoryPoint[];
  meals?: NutritionMeal[];
};

export type NutritionMeal = {
  meal_type: string;
  label: string;
  items: string[];
  kcal: number;
  recorded_at: string;
};

export function useAgentDetail(agentId: AgentId | null, enabled: boolean) {
  return useQuery<AgentDetail>({
    queryKey: ['agent-detail', agentId],
    queryFn: async () => {
      const { data, error, response } = await api.GET('/agents/{agent_id}/detail', {
        params: { path: { agent_id: agentId! as BackendAgentId } },
      });
      if (error) {
        console.error('[useAgentDetail] error', agentId, response?.status, JSON.stringify(error));
        throw error;
      }
      console.log('[useAgentDetail] ok', agentId, JSON.stringify(data));
      return data as AgentDetail;
    },
    enabled: enabled && hasAgentDetail(agentId),
    staleTime: 5 * 60 * 1000,
  });
}
