import { useState, useEffect } from "react";
import type { HealthSummary } from "../types";

interface UseHealthSummaryResult {
  data: HealthSummary | null;
  error: string | null;
  loading: boolean;
  refresh: () => void;
}

export function useHealthSummary(intervalMs = 120_000): UseHealthSummaryResult {
  const [data, setData] = useState<HealthSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function fetchSummary() {
      try {
        const resp = await fetch("/health-summary");
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const json: HealthSummary = await resp.json();
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

    fetchSummary();
    const id = setInterval(fetchSummary, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [intervalMs, tick]);

  const refresh = () => setTick(t => t + 1);

  return { data, error, loading, refresh };
}
