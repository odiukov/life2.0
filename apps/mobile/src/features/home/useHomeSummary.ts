import { useQuery } from '@tanstack/react-query';
import { useFocusEffect } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import type { AgentId } from '@life-agents/ui';
import { api, apiBaseUrl } from '@/api/client';
import { useSyncTimestamp } from '@/features/sync/syncTimestamp';

export type AgentTint = 'success' | 'warn' | 'danger' | 'neutral';

export type HomeAgent = {
  agent: AgentId;
  label: string;
  metric: string;
  detail: string | null;
  tint: AgentTint;
  progress: number | null;
  workoutType?: string;
};

export type HomeRings = {
  readyPct: number | null; // 0–100 recovery readiness; null when insufficient data
  hrvPct: number | null; // 0–100 ring fill (normalised vs 30d personal range)
  hrvMs: number | null; // raw HRV value in ms for display label
  stepsPct: number | null; // 0–100 today's steps vs 10 000 goal
  moodPct: number | null; // 0–100 mood score
};

export type FeaturedSleep = {
  durationLabel: string; // "6h 45m"
  durationPct: number; // 0–100 vs goal
  deepLabel: string; // "1h 12m"
  deepPct: number;
  hrv: number;
  avgHr: number;
  hrvDelta: string; // "+4 vs avg"
  source: string; // "Garmin"
  insight: string | null;
};

export type FeaturedWorkout = {
  sessionName: string; // "Zone 2 run"
  distanceKm: number;
  kcal: number;
  avgHr: number;
  source: string;
  extraCount: number; // additional sessions today
  loadHistory: number[]; // 7 values for sparkbars
  workoutDate: 'today' | 'yesterday';
  workoutAt?: string | null; // ISO timestamp of the most recent session, when known
};

export type FeaturedNutrition = {
  kcalConsumed: number;
  kcalGoal: number;
  proteinG: number;
  proteinGoalG: number;
  carbsG: number;
  carbsGoalG: number;
  fatG: number;
  fatGoalG: number;
  source: string;
  nutritionDate: 'today' | 'yesterday';
};

export type FeaturedBody = {
  weightKg: number;
  weightDelta30d: number | null;
  weightDeltaPrev: number | null;
  ageDaysLabel: string;
  source: string;
  sparkWeights: number[];
  fatPct: number | null;
  fatPctDelta30d: number | null;
  muscleKg: number | null;
  muscleKgDelta30d: number | null;
  leanKg: number | null;
  leanKgDelta30d: number | null;
};

export type HomeSummary = {
  agents: HomeAgent[];
  recovery?: string | null;
  rings?: HomeRings;
  featuredSleep?: FeaturedSleep | null;
  featuredWorkout?: FeaturedWorkout | null;
  featuredNutrition?: FeaturedNutrition | null;
  featuredBody?: FeaturedBody | null;
};

async function getTodayStepsPct(): Promise<number | null> {
  try {
    const hk = require('@kingstinct/react-native-healthkit') as {
      isHealthDataAvailable: () => boolean;
      queryQuantitySamples: (
        identifier: string,
        options: {
          filter: { date: { startDate: Date; endDate: Date } };
          limit: number;
          ascending: boolean;
          unit: string;
        },
      ) => Promise<readonly { quantity: number }[]>;
    };
    if (!hk.isHealthDataAvailable()) return null;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const samples = await hk.queryQuantitySamples('HKQuantityTypeIdentifierStepCount', {
      filter: { date: { startDate: today, endDate: new Date() } },
      limit: -1,
      ascending: true,
      unit: 'count',
    });
    const total = samples.reduce((sum, s) => sum + (s.quantity ?? 0), 0);
    return Math.min(100, Math.round((total / 10_000) * 100));
  } catch {
    return null;
  }
}

async function getLast30DHrv(): Promise<{ pct: number; ms: number } | null> {
  try {
    const hk = require('@kingstinct/react-native-healthkit') as {
      isHealthDataAvailable: () => boolean;
      queryQuantitySamples: (
        identifier: string,
        options: {
          filter: { date: { startDate: Date; endDate: Date } };
          limit: number;
          ascending: boolean;
          unit: string;
        },
      ) => Promise<readonly { quantity: number }[]>;
    };
    if (!hk.isHealthDataAvailable()) return null;
    const now = new Date();
    const ago30 = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    const samples = await hk.queryQuantitySamples(
      'HKQuantityTypeIdentifierHeartRateVariabilitySDNN',
      {
        filter: { date: { startDate: ago30, endDate: now } },
        limit: -1,
        ascending: false,
        unit: 'ms',
      },
    );
    if (samples.length === 0) return null;
    const ms = Math.round(samples[0]!.quantity);
    const vals = samples.map((s) => s.quantity);
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const pct = max <= min ? 50 : Math.round(((ms - min) / (max - min)) * 100);
    return { pct, ms };
  } catch {
    return null;
  }
}

async function triggerRemoteSync(): Promise<void> {
  const sync = useSyncTimestamp.getState();
  sync.setSyncing(true);
  try {
    const { getAuthHeaders } = await import('@/features/healthkit/sync');
    const headers = await getAuthHeaders();
    const res = await fetch(`${apiBaseUrl}/sync/trigger`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...headers },
    });
    if (!res.ok) throw new Error(`/sync/trigger failed: ${res.status}`);
  } finally {
    sync.markSynced();
  }
}

export function useHomeSummary() {
  const [isRefreshing, setIsRefreshing] = useState(false);
  const hasInitialized = useRef(false);

  const query = useQuery({
    queryKey: ['home-summary'],
    queryFn: async (): Promise<HomeSummary> => {
      const { data, error } = await api.GET('/dashboard/summary');
      if (error) throw error;
      const agents: HomeAgent[] = (data?.agents ?? []).map((a) => ({
        agent: a.agent as AgentId,
        label: a.label,
        metric: a.metric,
        detail: a.detail ?? null,
        tint: a.tint as AgentTint,
        progress: a.progress ?? null,
        workoutType: (a as any).workout_type ?? undefined,
      }));
      const raw = data as any;
      const [hkStepsPct, hkHrv] = await Promise.all([getTodayStepsPct(), getLast30DHrv()]);
      return {
        agents,
        recovery: raw?.recovery ?? null,
        rings: raw?.rings
          ? (() => {
              // Prefer backend (Garmin HRV Status RMSSD via /dashboard/summary).
              // HealthKit holds whatever Garmin Connect / Apple Watch synced — for
              // Garmin users that's the sleep-DTO averageHRV, a different metric
              // than the one shown on the watch widget.
              const apiHrvMs: number | null = raw.rings.hrvMs ?? null;
              const hrvMs = apiHrvMs ?? hkHrv?.ms ?? null;
              const hrvPct =
                raw.rings.hrvPct ??
                hkHrv?.pct ??
                (hrvMs != null ? Math.min(100, Math.round((hrvMs / 80) * 100)) : null);
              return {
                readyPct: raw.rings.readyPct ?? null,
                hrvPct,
                hrvMs,
                stepsPct: raw.rings.stepsPct ?? hkStepsPct ?? null,
                moodPct: raw.rings.moodPct ?? null,
              };
            })()
          : undefined,
        featuredSleep: raw?.featured_sleep ?? null,
        featuredWorkout: raw?.featured_workout ?? null,
        featuredNutrition: raw?.featured_nutrition ?? null,
        featuredBody: raw?.featured_body ?? null,
      };
    },
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });

  useFocusEffect(
    useCallback(() => {
      if (hasInitialized.current) return;
      hasInitialized.current = true;
      import('@/features/healthkit/sync')
        .then((m) => m.runSync())
        .catch(() => {})
        .finally(() => query.refetch());
    }, []),
  );

  const onRefresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const { runSync } = await import('@/features/healthkit/sync');
      await runSync({ force: true }).catch((e) =>
        console.warn('[useHomeSummary] runSync failed:', e),
      );
      await triggerRemoteSync().catch((e) =>
        console.warn('[useHomeSummary] triggerRemoteSync failed:', e),
      );
      await query.refetch();
    } finally {
      setIsRefreshing(false);
    }
  }, [query.refetch]);

  return { ...query, isRefreshing, onRefresh };
}
