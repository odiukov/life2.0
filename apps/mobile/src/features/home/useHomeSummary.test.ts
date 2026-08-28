import React from 'react';
import { renderHook, act, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useHomeSummary } from './useHomeSummary';

// expo-router is already mocked via jest.config.ts moduleNameMapper →
// src/__mocks__/expo-router.tsx which calls useFocusEffect once on mount.

jest.mock('@/api/client', () => ({
  api: {
    GET: jest.fn().mockResolvedValue({
      data: { agents: [], rings: null },
      error: null,
    }),
  },
  apiBaseUrl: 'http://localhost:8000',
}));

jest.mock('@/features/auth/SupabaseClient', () => ({
  SUPABASE_CONFIGURED: false,
  supabase: {
    auth: { getSession: jest.fn().mockResolvedValue({ data: { session: null } }) },
  },
}));

// Dynamic import in the hook is also intercepted by jest.mock
jest.mock('@/features/healthkit/sync', () => ({
  runSync: jest.fn().mockResolvedValue({ uploaded: 0 }),
  getAuthHeaders: jest.fn().mockResolvedValue({}),
}));

jest.mock(
  '@kingstinct/react-native-healthkit',
  () => ({
    isHealthDataAvailable: jest.fn().mockReturnValue(true),
    queryQuantitySamples: jest.fn().mockResolvedValue([{ quantity: 6000 }, { quantity: 2000 }]),
  }),
  { virtual: true },
);

const mockFetch = jest.fn().mockResolvedValue({ ok: true, status: 200 });
global.fetch = mockFetch as unknown as typeof fetch;

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return React.createElement(QueryClientProvider, { client: qc }, children);
}

describe('useHomeSummary', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (require('@/api/client').api.GET as jest.Mock).mockResolvedValue({
      data: { agents: [], rings: null },
      error: null,
    });
    mockFetch.mockResolvedValue({ ok: true, status: 200 });
    (require('@/features/healthkit/sync').runSync as jest.Mock).mockResolvedValue({ uploaded: 0 });
  });

  it('starts with isRefreshing false', async () => {
    const { result } = renderHook(() => useHomeSummary(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isRefreshing).toBe(false);
  });

  it('isRefreshing returns to false after onRefresh completes', async () => {
    const { result } = renderHook(() => useHomeSummary(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.onRefresh();
    });

    expect(result.current.isRefreshing).toBe(false);
  });

  it('onRefresh calls runSync then POST /sync/trigger', async () => {
    const { result } = renderHook(() => useHomeSummary(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    // Clear counts accumulated during mount (focus effect fires runSync once on init)
    jest.clearAllMocks();
    mockFetch.mockResolvedValue({ ok: true, status: 200 });
    (require('@/features/healthkit/sync').runSync as jest.Mock).mockResolvedValue({ uploaded: 0 });
    (require('@/features/healthkit/sync').getAuthHeaders as jest.Mock).mockResolvedValue({});

    await act(async () => {
      await result.current.onRefresh();
    });

    const { runSync } = require('@/features/healthkit/sync');
    expect(runSync).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/sync/trigger',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('data is not stale immediately after load (staleTime Infinity)', async () => {
    const { result } = renderHook(() => useHomeSummary(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isStale).toBe(false);
  });

  it('maps new ring fields from API response', async () => {
    (require('@/api/client').api.GET as jest.Mock).mockResolvedValue({
      data: {
        agents: [],
        rings: { readyPct: 65, hrvPct: 50, stepsPct: 40, moodPct: 70 },
      },
      error: null,
    });
    const { result } = renderHook(() => useHomeSummary(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data?.rings).toEqual({
      readyPct: 65,
      hrvPct: 50,
      stepsPct: 80,
      moodPct: 70,
    });
  });

  it('HRV ring prefers API (Garmin HRV Status) over HealthKit', async () => {
    // Backend returns 38 (hrv_status.hrv_rmssd, the Garmin watch widget value).
    // HealthKit mock returns 6000 (samples[0]) — this is what Garmin Connect
    // syncs into Apple Health (sleep-DTO averageHRV, a different metric).
    // Backend must win.
    (require('@/api/client').api.GET as jest.Mock).mockResolvedValue({
      data: {
        agents: [],
        rings: { readyPct: 65, hrvPct: 42, hrvMs: 38, stepsPct: 30, moodPct: 70 },
      },
      error: null,
    });
    const { result } = renderHook(() => useHomeSummary(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data?.rings?.hrvMs).toBe(38);
    expect(result.current.data?.rings?.hrvPct).toBe(42);
  });

  it('HRV ring falls back to HealthKit when API has no HRV', async () => {
    (require('@/api/client').api.GET as jest.Mock).mockResolvedValue({
      data: {
        agents: [],
        rings: { readyPct: 65, hrvPct: null, hrvMs: null, stepsPct: 30, moodPct: 70 },
      },
      error: null,
    });
    const { result } = renderHook(() => useHomeSummary(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    // HK mock: samples[0]=6000 → ms=6000, pct=100 (max-normalised across 2 samples)
    expect(result.current.data?.rings?.hrvMs).toBe(6000);
    expect(result.current.data?.rings?.hrvPct).toBe(100);
  });

  it('steps ring prefers HealthKit (6000+2000=8000 → 80%)', async () => {
    (require('@/api/client').api.GET as jest.Mock).mockResolvedValue({
      data: {
        agents: [],
        rings: { readyPct: 65, hrvPct: 50, stepsPct: 30, moodPct: 70 },
      },
      error: null,
    });
    const { result } = renderHook(() => useHomeSummary(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data?.rings?.stepsPct).toBe(80);
  });

  it('steps ring falls back to API when HealthKit unavailable', async () => {
    const hk = require('@kingstinct/react-native-healthkit');
    (hk.isHealthDataAvailable as jest.Mock).mockReturnValue(false);
    (require('@/api/client').api.GET as jest.Mock).mockResolvedValue({
      data: {
        agents: [],
        rings: { readyPct: 65, hrvPct: 50, stepsPct: 30, moodPct: 70 },
      },
      error: null,
    });
    const { result } = renderHook(() => useHomeSummary(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data?.rings?.stepsPct).toBe(30);
  });

  it('maps featured_body field from API response', async () => {
    (require('@/api/client').api.GET as jest.Mock).mockResolvedValue({
      data: {
        agents: [],
        rings: null,
        featured_body: {
          weightKg: 78.4,
          weightDelta30d: -1.2,
          weightDeltaPrev: -0.6,
          ageDaysLabel: '3 days ago',
          source: 'ViHealth',
          sparkWeights: [79.6, 78.4],
          fatPct: 22.1,
          fatPctDelta30d: -0.8,
          muscleKg: 38.5,
          muscleKgDelta30d: 0.1,
          leanKg: 61.1,
          leanKgDelta30d: -0.4,
        },
      },
      error: null,
    });
    const { result } = renderHook(() => useHomeSummary(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data?.featuredBody).toEqual({
      weightKg: 78.4,
      weightDelta30d: -1.2,
      weightDeltaPrev: -0.6,
      ageDaysLabel: '3 days ago',
      source: 'ViHealth',
      sparkWeights: [79.6, 78.4],
      fatPct: 22.1,
      fatPctDelta30d: -0.8,
      muscleKg: 38.5,
      muscleKgDelta30d: 0.1,
      leanKg: 61.1,
      leanKgDelta30d: -0.4,
    });
  });

  it('featured_body is null when API omits it', async () => {
    const { result } = renderHook(() => useHomeSummary(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data?.featuredBody ?? null).toBeNull();
  });
});
