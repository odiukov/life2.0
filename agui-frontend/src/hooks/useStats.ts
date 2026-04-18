import { useState, useEffect } from "react";
import type { StatsResponse } from "../types";

interface UseStatsResult {
  data: StatsResponse | null;
  error: string | null;
  loading: boolean;
  refresh: () => void;
}

export function useStats(intervalMs = 60_000): UseStatsResult {
  const [data, setData] = useState<StatsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function fetchStats() {
      try {
        const resp = await fetch("/api/stats");
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const json: StatsResponse = await resp.json();
        if (!cancelled) {
          setData(json);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchStats();
    const id = setInterval(fetchStats, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [intervalMs, tick]);

  const refresh = () => setTick(t => t + 1);

  return { data, error, loading, refresh };
}
