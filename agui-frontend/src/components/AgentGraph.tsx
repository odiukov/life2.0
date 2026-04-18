import type { AgentInfo } from "../types";

const AGENT_CONFIG: Record<string, { emoji: string; color: string }> = {
  sleep:     { emoji: "😴", color: "#4a9eff" },
  workout:   { emoji: "💪", color: "#4eff9a" },
  nutrition: { emoji: "🥗", color: "#ffb74a" },
};

const PEER_EDGES: [string, string][] = [
  ["sleep", "workout"],
  ["workout", "nutrition"],
  ["sleep", "nutrition"],
];

const CARD_WIDTH = 100;
const CARD_GAP = 16;
const cardCenterX = (i: number) => i * (CARD_WIDTH + CARD_GAP) + CARD_WIDTH / 2;
const rowWidth = (n: number) => n * CARD_WIDTH + (n - 1) * CARD_GAP;

interface Props {
  agents: AgentInfo[];
  selectedAgent: string | null;
  highlightedAgent?: string | null;
  onSelect: (name: string | null) => void;
}

export function AgentGraph({ agents, selectedAgent, highlightedAgent, onSelect }: Props) {
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
      {/* Top tier: orchestrator + MCP services */}
      <div style={{ display: "flex", gap: 24, alignItems: "center" }}>
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

        <div style={{
          background: "#16213e",
          border: "1px dashed #666",
          borderRadius: 8,
          padding: "12px 20px",
          textAlign: "center",
          color: "#888",
          opacity: 0.85,
        }}>
          <div style={{ fontSize: 9, opacity: 0.7, marginBottom: 2 }}>calendar-mcp</div>
          <div style={{ fontSize: 11, fontWeight: "bold" }}>:9100</div>
          <div style={{ fontSize: 9, color: "#555", marginTop: 4 }}>MCP</div>
        </div>
      </div>

      {/* Connection lines SVG */}
      <svg width={rowWidth(agents.length)} height={32} style={{ overflow: "visible" }}>
        {agents.map((_, i) => (
          <line
            key={i}
            x1={rowWidth(agents.length) / 2} y1={0}
            x2={cardCenterX(i)} y2={32}
            stroke="#3a5a8a"
            strokeWidth={1.5}
            strokeDasharray="4,4"
          />
        ))}
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
                ...(highlightedAgent === agent.name
                  ? { outline: "2px solid #4a9eff", outlineOffset: "3px" }
                  : {}),
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

      {/* Peer consult edges — drawn below the agent-nodes row */}
      <svg
        width={rowWidth(agents.length)}
        height={48}
        style={{ overflow: "visible", marginTop: -4 }}
      >
        {PEER_EDGES.map(([a, b]) => {
          const ia = agents.findIndex(ag => ag.name === a);
          const ib = agents.findIndex(ag => ag.name === b);
          if (ia < 0 || ib < 0) return null;
          const xa = cardCenterX(ia);
          const xb = cardCenterX(ib);
          const midX = (xa + xb) / 2;
          const dip = 16 + Math.abs(ia - ib) * 8;
          return (
            <path
              key={`${a}-${b}`}
              data-peer-edge={`${a}-${b}`}
              d={`M ${xa} 0 Q ${midX} ${dip} ${xb} 0`}
              stroke="#6a7a9a"
              strokeWidth={1.25}
              strokeDasharray="2,3"
              fill="none"
              opacity={0.8}
            />
          );
        })}
      </svg>

      {/* Legend */}
      <div style={{ display: "flex", gap: 16, fontSize: 9, color: "#555", marginTop: 8 }}>
        <span>┄┄ orchestrator→agent</span>
        <span>┈┈ peer consult</span>
        <span>▫ MCP</span>
      </div>
    </div>
  );
}
