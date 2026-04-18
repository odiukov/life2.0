import { useState, useEffect } from "react";
import type { AgentInfo, AgentsResponse } from "../types";

interface UseAgentsResult {
  agents: AgentInfo[];
  error: string | null;
  loading: boolean;
}

export function useAgents(intervalMs = 10_000): UseAgentsResult {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function fetchAgents() {
      try {
        const resp = await fetch("/api/agents");
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const json: AgentsResponse = await resp.json();
        if (!cancelled) {
          setAgents(json.agents);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchAgents();
    const id = setInterval(fetchAgents, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [intervalMs]);

  return { agents, error, loading };
}
