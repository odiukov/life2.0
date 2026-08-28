import React from 'react';
import { renderHook, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useAgentStatusRows } from './useAgentStatusRows';

jest.mock('@/features/home/useHomeSummary', () => ({
  useHomeSummary: () => ({
    data: {
      agents: [
        { agent: 'sleep', metric: '7h 10m', detail: 'HRV 62' },
        { agent: 'mood', metric: null, detail: null },
      ],
      rings: { readyPct: 80, hrvPct: 70, stepsPct: 60, moodPct: null },
    },
    isLoading: false,
    isError: false,
  }),
}));

jest.mock('@/features/integrations/store', () => ({
  useConnectedIntegrations: () => new Set(['appleHealth']),
}));

jest.mock('@/features/profile/useMeProfile', () => ({
  useMeProfile: () => ({ data: null, isLoading: false }),
}));

jest.mock('@/features/sync/syncTimestamp', () => ({
  useSyncTimestamp: (
    selector: (s: { lastSyncedAt: number | null; isSyncing: boolean }) => unknown,
  ) => selector({ lastSyncedAt: null, isSyncing: false }),
}));

jest.mock('@/features/healthkit/sync', () => ({
  getAuthHeaders: () => Promise.resolve({}),
}));

jest.mock('@/api/client', () => ({
  apiBaseUrl: 'http://localhost:8000',
}));

// Mock fetch so the agentsQuery doesn't fail
global.fetch = jest.fn(() =>
  Promise.resolve({
    ok: true,
    json: () => Promise.resolve({ agents: [] }),
  } as Response),
);

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return React.createElement(QueryClientProvider, { client: qc }, children);
}

describe('useAgentStatusRows', () => {
  it('returns rows for all agents', async () => {
    const { result } = renderHook(() => useAgentStatusRows(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.rows.length).toBeGreaterThan(0);
  });

  it('computes readyCount and totalCount', async () => {
    const { result } = renderHook(() => useAgentStatusRows(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.totalCount).toBeGreaterThan(0);
    expect(result.current.readyCount).toBeGreaterThanOrEqual(0);
    expect(result.current.readyCount).toBeLessThanOrEqual(result.current.totalCount);
  });

  it('each row has id, status, hint', async () => {
    const { result } = renderHook(() => useAgentStatusRows(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    for (const row of result.current.rows) {
      expect(row).toHaveProperty('id');
      expect(row).toHaveProperty('status');
      expect(row).toHaveProperty('hint');
    }
  });
});
