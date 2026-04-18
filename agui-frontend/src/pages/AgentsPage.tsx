import { useState } from "react";
import { useLocation } from "react-router-dom";
import { AgentGraph } from "../components/AgentGraph";
import { TopologyDetailPane } from "../components/TopologyDetailPane";
import { useAgents } from "../hooks/useAgents";
import { useStats } from "../hooks/useStats";
import type { Selection } from "../types";

export default function AgentsPage() {
  const { agents, loading, error } = useAgents();
  const { data: stats } = useStats();
  const [selected, setSelected] = useState<Selection>(null);
  const location = useLocation();
  const highlighted: string | null =
    (location.state as { highlighted?: string } | null)?.highlighted ?? null;

  if (loading) {
    return <div style={{ padding: 32, color: "#555", fontFamily: "monospace" }}>Discovering agents...</div>;
  }

  if (error) {
    return <div style={{ padding: 32, color: "#e57373", fontFamily: "monospace" }}>Error: {error}</div>;
  }

  return (
    <div style={{ display: "flex", height: "calc(100vh - 41px)", overflow: "hidden" }}>
      <TopologyDetailPane
        selected={selected}
        agents={agents}
        stats={stats}
        onClose={() => setSelected(null)}
      />
      <div style={{ flex: 1, overflow: "auto", padding: 32, display: "flex", flexDirection: "column", alignItems: "center", gap: 24 }}>
        <h2 style={{ color: "#e0e0e0", fontFamily: "monospace", fontWeight: "normal", margin: 0 }}>
          Topology
        </h2>
        <AgentGraph
          agents={agents}
          selected={selected}
          highlightedAgent={highlighted}
          onSelect={setSelected}
        />
      </div>
    </div>
  );
}
