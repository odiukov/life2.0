import { useState } from "react";
import { AgentGraph } from "../components/AgentGraph";
import { AgentCard } from "../components/AgentCard";
import { useAgents } from "../hooks/useAgents";
import type { AgentInfo } from "../types";

export default function AgentsPage() {
  const { agents, loading, error } = useAgents();
  const [selected, setSelected] = useState<string | null>(null);

  const selectedAgent: AgentInfo | undefined = agents.find(a => a.name === selected);

  if (loading) {
    return <div style={{ padding: 32, color: "#555", fontFamily: "monospace" }}>Discovering agents...</div>;
  }

  if (error) {
    return <div style={{ padding: 32, color: "#e57373", fontFamily: "monospace" }}>Error: {error}</div>;
  }

  return (
    <div style={{ padding: 32, display: "flex", flexDirection: "column", alignItems: "center", gap: 24 }}>
      <h2 style={{ color: "#e0e0e0", fontFamily: "monospace", fontWeight: "normal", margin: 0 }}>
        Agent Topology
      </h2>
      <AgentGraph agents={agents} selectedAgent={selected} onSelect={setSelected} />
      {selectedAgent && (
        <AgentCard agent={selectedAgent} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
