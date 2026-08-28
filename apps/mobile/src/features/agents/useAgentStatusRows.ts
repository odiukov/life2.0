import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import type { AgentId } from '@life-agents/ui';
import { apiBaseUrl } from '@/api/client';
import { getAuthHeaders } from '@/features/healthkit/sync';
import { useConnectedIntegrations } from '@/features/integrations/store';
import { useHomeSummary, type HomeSummary } from '@/features/home/useHomeSummary';
import { useMeProfile } from '@/features/profile/useMeProfile';
import { useSyncTimestamp } from '@/features/sync/syncTimestamp';
import { AGENT_DISPLAY_ORDER, computeAgentStatus, type AgentRow } from './agentStatusRules';
import { AGENT_COPY } from './agentCopy';

export type AgentStatusRows = {
  rows: AgentRow[];
  readyCount: number;
  totalCount: number;
  lastSyncedAt: number | null;
  isSyncing: boolean;
  isLoading: boolean;
};

type AgentsResponse = {
  agents: { name: string; online: boolean }[];
};

export function useAgentStatusRows(): AgentStatusRows {
  const integrations = useConnectedIntegrations();
  const summaryQuery = useHomeSummary();
  const profileQuery = useMeProfile();
  const lastSyncedAt = useSyncTimestamp((s) => s.lastSyncedAt);
  const isSyncing = useSyncTimestamp((s) => s.isSyncing);

  const agentsQuery = useQuery<AgentsResponse>({
    queryKey: ['agents'],
    queryFn: async () => {
      const headers = await getAuthHeaders();
      const res = await fetch(`${apiBaseUrl}/agents`, { headers });
      if (!res.ok) throw new Error(`GET /agents failed: ${res.status}`);
      return (await res.json()) as AgentsResponse;
    },
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const peerOnline = useMemo(() => {
    const m = new Map<string, boolean>();
    for (const a of agentsQuery.data?.agents ?? []) m.set(a.name, a.online);
    return m;
  }, [agentsQuery.data]);

  const summary: HomeSummary | undefined = summaryQuery.data;
  const meProfile = profileQuery.data;

  const rows: AgentRow[] = useMemo(() => {
    return AGENT_DISPLAY_ORDER.map((id: AgentId) => {
      const r = computeAgentStatus(id, { integrations, summary, peerOnline, meProfile });
      return {
        id,
        description: AGENT_COPY[id].description,
        status: r.status,
        hint: r.hint,
        cta: r.cta,
      };
    });
  }, [integrations, summary, peerOnline, meProfile]);

  const readyCount = rows.filter((r) => r.status === 'ready').length;

  return {
    rows,
    readyCount,
    totalCount: rows.length,
    lastSyncedAt,
    isSyncing,
    isLoading: agentsQuery.isLoading || summaryQuery.isLoading || profileQuery.isLoading,
  };
}
