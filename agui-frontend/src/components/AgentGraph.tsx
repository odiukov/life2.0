import type { AgentInfo } from "../types";

const AGENT_CONFIG: Record<string, { emoji: string; color: string }> = {
  sleep:     { emoji: "😴", color: "#4a9eff" },
  workout:   { emoji: "💪", color: "#4eff9a" },
  nutrition: { emoji: "🥗", color: "#ffb74a" },
};

interface Props {
  agents: AgentInfo[];
  selectedAgent: string | null;
  onSelect: (name: string | null) => void;
}

export function AgentGraph({ agents, selectedAgent, onSelect }: Props) {
  const onlineCount = agents.filter(a => a.online).length;

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      gap: 24,
      padding: "32px 16px",
      fontFamily: "monospace",
    }}>
      {/* Orchestrator node */}
      <div style={{
        background: "#0f3460",
        border: "1px solid #4a9eff",
        borderRadius: 8,
        padding: "12px 28px",
        textAlign: "center",
        color: "#4a9eff",
      }}>
        <div style={{ fontSize: 9, opacity: 0.7, marginBottom: 2 }}>orchestrator</div>
        <div style={{ fontSize: 11, fontWeight: "bold" }}>:8000</div>
        <div style={{ fontSize: 9, color: "#555", marginTop: 4 }}>{onlineCount}/{agents.length} agents online</div>
      </div>

      {/* Connection lines SVG */}
      <svg width={agents.length * 120} height={32} style={{ overflow: "visible" }}>
        {agents.map((_, i) => {
          const totalW = agents.length * 120;
          const x = (i + 0.5) * (totalW / agents.length);
          return (
            <line
              key={i}
              x1={totalW / 2} y1={0}
              x2={x} y2={32}
              stroke="#3a5a8a"
              strokeWidth={1.5}
              strokeDasharray="4,4"
            />
          );
        })}
      </svg>

      {/* Agent nodes */}
      <div style={{ display: "flex", gap: 16 }}>
        {agents.map(agent => {
          const cfg = AGENT_CONFIG[agent.name] ?? { emoji: "🤖", color: "#aaa" };
          const isSelected = selectedAgent === agent.name;
          return (
            <div
              key={agent.name}
              onClick={() => onSelect(isSelected ? null : agent.name)}
              style={{
                background: "#16213e",
                border: `1px solid ${isSelected ? cfg.color : (agent.online ? "#1e3a1e" : "#3a1e1e")}`,
                borderRadius: 8,
                padding: "14px 18px",
                textAlign: "center",
                width: 100,
                cursor: "pointer",
                transition: "border-color 0.15s",
              }}
            >
              <div style={{ fontSize: 22 }}>{cfg.emoji}</div>
              <div style={{ color: "#aaa", marginTop: 4, fontSize: 10 }}>{agent.name}</div>
              <div style={{ color: "#555", fontSize: 9 }}>:{agent.url.split(":").pop()}</div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 4, marginTop: 6 }}>
                <div style={{ width: 6, height: 6, borderRadius: "50%", background: agent.online ? "#4eff9a" : "#e57373" }} />
                <div style={{ fontSize: 8, color: agent.online ? "#4eff9a" : "#e57373" }}>
                  {agent.online ? "online" : "offline"}
                </div>
              </div>
              <div style={{ fontSize: 9, color: "#555", marginTop: 4 }}>{agent.tasks_today} tasks today</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
