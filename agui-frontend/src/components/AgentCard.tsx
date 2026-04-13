import type { AgentInfo } from "../types";

const AGENT_CONFIG: Record<string, { emoji: string; color: string }> = {
  sleep:     { emoji: "😴", color: "#4a9eff" },
  workout:   { emoji: "💪", color: "#4eff9a" },
  nutrition: { emoji: "🥗", color: "#ffb74a" },
};

interface Props {
  agent: AgentInfo;
  onClose: () => void;
}

export function AgentCard({ agent, onClose }: Props) {
  const cfg = AGENT_CONFIG[agent.name] ?? { emoji: "🤖", color: "#aaa" };
  return (
    <div style={{
      background: "#13131f",
      border: "1px solid #1e1e30",
      borderRadius: 8,
      padding: "16px 20px",
      width: 300,
      fontFamily: "monospace",
      color: "#e0e0e0",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 20 }}>{cfg.emoji}</span>
          <span style={{ fontSize: 13, fontWeight: "bold" }}>{agent.name}-agent</span>
        </div>
        <button
          onClick={onClose}
          style={{ background: "none", border: "none", color: "#555", cursor: "pointer", fontSize: 16 }}
        >
          ×
        </button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 11 }}>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span style={{ color: "#555" }}>Status</span>
          <span style={{ color: agent.online ? "#4eff9a" : "#e57373" }}>
            {agent.online ? "● online" : "● offline"}
          </span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span style={{ color: "#555" }}>Port</span>
          <span>{agent.url.split(":").pop()}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span style={{ color: "#555" }}>Tasks today</span>
          <span style={{ color: cfg.color }}>{agent.tasks_today}</span>
        </div>
        {agent.description && (
          <div style={{ color: "#888", fontSize: 10, marginTop: 4 }}>{agent.description}</div>
        )}
        <div style={{ marginTop: 8 }}>
          <div style={{ color: "#555", fontSize: 9, textTransform: "uppercase", letterSpacing: 1, marginBottom: 6 }}>Capabilities</div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {agent.capabilities.map(cap => (
              <span key={cap} style={{
                background: "#0f3460",
                borderRadius: 10,
                padding: "3px 8px",
                fontSize: 9,
                color: cfg.color,
              }}>
                {cap}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
