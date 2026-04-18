import { AGENT_COLORS, type AgentKey, type AgentInfo, type Selection } from "../types";

const PEER_EDGES: [AgentKey, AgentKey][] = [
  ["sleep", "workout"],
  ["workout", "nutrition"],
  ["sleep", "nutrition"],
];

const TOOL_NODES = [
  { name: "calendar-mcp", port: ":9100" },
];

const CARD_WIDTH = 120;
const CARD_GAP = 12;
const AGENT_STACK_HEIGHT = 3 * 90 + 2 * CARD_GAP;

interface Props {
  agents: AgentInfo[];
  selected: Selection;
  highlightedAgent?: string | null;
  onSelect: (sel: Selection) => void;
}

const COLUMN_STYLE: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: CARD_GAP,
  alignItems: "center",
  justifyContent: "center",
};

const NODE_CARD_BASE: React.CSSProperties = {
  background: "#16213e",
  borderRadius: 8,
  padding: "12px 16px",
  textAlign: "center",
  cursor: "pointer",
  transition: "border-color 0.15s",
  width: CARD_WIDTH,
  boxSizing: "border-box",
};

const PROTOCOL_LABEL: React.CSSProperties = {
  fontSize: 10,
  color: "#888",
  fontFamily: "monospace",
  letterSpacing: 1,
};

export function AgentGraph({ agents, selected, highlightedAgent, onSelect }: Props) {
  const onlineCount = agents.filter(a => a.online).length;
  const orchestratorSelected = selected?.kind === "orchestrator";

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 24, padding: "32px 16px", fontFamily: "monospace", flexWrap: "wrap", justifyContent: "center" }}>
      {/* USER column */}
      <div style={COLUMN_STYLE}>
        <div style={{ ...NODE_CARD_BASE, cursor: "default", border: "1px solid #2a2a40" }}>
          <div style={{ fontSize: 22 }}>👤</div>
          <div style={{ color: "#aaa", marginTop: 4, fontSize: 11 }}>USER</div>
        </div>
      </div>

      {/* AG-UI link */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
        <span style={PROTOCOL_LABEL}>AG-UI</span>
        <svg width={60} height={12} style={{ overflow: "visible" }}>
          <defs>
            <marker id="arrow-agui" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
              <path d="M0,0 L10,5 L0,10 z" fill="#4a9eff" />
            </marker>
          </defs>
          <line x1={0} y1={6} x2={54} y2={6} stroke="#4a9eff" strokeWidth={1.5} markerEnd="url(#arrow-agui)" />
        </svg>
      </div>

      {/* AGENT column */}
      <div style={COLUMN_STYLE}>
        <div
          onClick={() => onSelect(orchestratorSelected ? null : { kind: "orchestrator" })}
          data-node="orchestrator"
          style={{
            ...NODE_CARD_BASE,
            background: "#0f3460",
            border: `1px solid ${orchestratorSelected ? "#80c0ff" : "#4a9eff"}`,
            color: "#4a9eff",
          }}
        >
          <div style={{ fontSize: 22 }}>🤖</div>
          <div style={{ fontSize: 11, fontWeight: "bold", marginTop: 4 }}>orchestrator</div>
          <div style={{ fontSize: 9, color: "#6aa", marginTop: 2 }}>:8000</div>
          <div style={{ fontSize: 9, color: "#555", marginTop: 4 }}>{onlineCount}/{agents.length} agents online</div>
        </div>
      </div>

      {/* MCP + A2A links */}
      <div style={{ display: "flex", flexDirection: "column", gap: CARD_GAP, alignItems: "center", justifyContent: "center", height: AGENT_STACK_HEIGHT }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
          <span style={PROTOCOL_LABEL}>MCP</span>
          <svg width={60} height={12} style={{ overflow: "visible" }}>
            <defs>
              <marker id="arrow-mcp" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
                <path d="M0,0 L10,5 L0,10 z" fill="#888" />
              </marker>
            </defs>
            <line x1={0} y1={6} x2={54} y2={6} stroke="#888" strokeWidth={1.5} strokeDasharray="4,3" markerEnd="url(#arrow-mcp)" />
          </svg>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
          <span style={PROTOCOL_LABEL}>A2A</span>
          <svg width={60} height={12} style={{ overflow: "visible" }}>
            <defs>
              <marker id="arrow-a2a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
                <path d="M0,0 L10,5 L0,10 z" fill="#6a7a9a" />
              </marker>
            </defs>
            <line x1={0} y1={6} x2={54} y2={6} stroke="#6a7a9a" strokeWidth={1.5} strokeDasharray="4,3" markerEnd="url(#arrow-a2a)" />
          </svg>
        </div>
      </div>

      {/* TOOLS + AGENTS column */}
      <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
        {/* TOOLS cluster */}
        <div style={COLUMN_STYLE}>
          <div style={{ fontSize: 9, color: "#555", letterSpacing: 1 }}>TOOLS</div>
          {TOOL_NODES.map(tool => {
            const isSelected = selected?.kind === "tool" && selected.name === tool.name;
            return (
              <div
                key={tool.name}
                onClick={() => onSelect(isSelected ? null : { kind: "tool", name: tool.name })}
                data-node={`tool-${tool.name}`}
                style={{
                  ...NODE_CARD_BASE,
                  border: `1px ${isSelected ? "solid" : "dashed"} ${isSelected ? "#aaa" : "#666"}`,
                  opacity: 0.9,
                }}
              >
                <div style={{ fontSize: 22 }}>🔧</div>
                <div style={{ color: "#aaa", marginTop: 4, fontSize: 11 }}>{tool.name}</div>
                <div style={{ color: "#555", fontSize: 9 }}>{tool.port}</div>
              </div>
            );
          })}
        </div>

        {/* AGENTS cluster */}
        <div style={{ position: "relative" }}>
          <div style={{ fontSize: 9, color: "#555", letterSpacing: 1, textAlign: "center", marginBottom: 6 }}>AGENTS</div>
          <div style={{ ...COLUMN_STYLE, gap: CARD_GAP }}>
            {agents.map(agent => {
              const cfg = AGENT_COLORS[agent.name as AgentKey] ?? { emoji: "🤖", color: "#aaa", label: agent.name };
              const isSelected = selected?.kind === "agent" && selected.name === agent.name;
              const isHighlighted = highlightedAgent === agent.name;
              return (
                <div
                  key={agent.name}
                  data-agent-name={agent.name}
                  onClick={() => onSelect(isSelected ? null : { kind: "agent", name: agent.name as AgentKey })}
                  style={{
                    ...NODE_CARD_BASE,
                    border: `1px solid ${isSelected ? cfg.color : (agent.online ? "#1e3a1e" : "#3a1e1e")}`,
                    ...(isHighlighted ? { outline: "2px solid #4a9eff", outlineOffset: 3 } : {}),
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8, justifyContent: "center" }}>
                    <span style={{ fontSize: 20 }}>{cfg.emoji}</span>
                    <div style={{ textAlign: "left" }}>
                      <div style={{ color: "#aaa", fontSize: 10 }}>{agent.name}</div>
                      <div style={{ color: "#555", fontSize: 9 }}>:{agent.url.split(":").pop()}</div>
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 4, marginTop: 6 }}>
                    <div style={{ width: 6, height: 6, borderRadius: "50%", background: agent.online ? "#4eff9a" : "#e57373" }} />
                    <div style={{ fontSize: 8, color: agent.online ? "#4eff9a" : "#e57373" }}>
                      {agent.online ? "online" : "offline"}
                    </div>
                    <div style={{ fontSize: 8, color: "#555", marginLeft: 6 }}>{agent.tasks_today} today</div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* A2A peer-edges drawn over the stack as curved SVG lines on the left side */}
          <svg
            width={28}
            height={AGENT_STACK_HEIGHT}
            style={{ position: "absolute", left: -32, top: 21, overflow: "visible", pointerEvents: "none" }}
          >
            {PEER_EDGES.map(([a, b]) => {
              const ia = agents.findIndex(x => x.name === a);
              const ib = agents.findIndex(x => x.name === b);
              if (ia < 0 || ib < 0) return null;
              const rowH = 90 + CARD_GAP;
              const ya = ia * rowH + 45;
              const yb = ib * rowH + 45;
              const midY = (ya + yb) / 2;
              const bulge = 16 + Math.abs(ia - ib) * 8;
              return (
                <path
                  key={`${a}-${b}`}
                  data-peer-edge={`${a}-${b}`}
                  d={`M 24 ${ya} Q ${24 - bulge} ${midY} 24 ${yb}`}
                  stroke="#6a7a9a"
                  strokeWidth={1.25}
                  strokeDasharray="2,3"
                  fill="none"
                  opacity={0.8}
                />
              );
            })}
          </svg>
        </div>
      </div>
    </div>
  );
}
