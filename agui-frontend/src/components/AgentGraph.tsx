import { AGENT_COLORS, TOOL_NODES, peersOf, type AgentKey, type AgentInfo, type Selection } from "../types";

const CARD_WIDTH = 120;
const CARD_GAP = 12;

interface Props {
  agents: AgentInfo[];
  selected: Selection;
  highlightedAgent?: string | null;
  onSelect: (sel: Selection) => void;
}

const NODE_CARD_BASE: React.CSSProperties = {
  background: "#16213e",
  borderRadius: 8,
  padding: "12px 16px",
  textAlign: "center",
  cursor: "pointer",
  transition: "box-shadow 0.18s, opacity 0.18s, border-color 0.15s, transform 0.15s",
  width: CARD_WIDTH,
  boxSizing: "border-box",
};

const PROTOCOL_LABEL: React.CSSProperties = {
  fontSize: 10,
  color: "#888",
  fontFamily: "monospace",
  letterSpacing: 1,
};

const CLUSTER_LABEL: React.CSSProperties = {
  fontSize: 9,
  color: "#555",
  letterSpacing: 1,
};

type GlowState = "strong" | "peer" | "dim" | "none";

function glowStyle(state: GlowState, color: string): React.CSSProperties {
  switch (state) {
    case "strong":
      return { boxShadow: `0 0 20px ${color}aa, 0 0 4px ${color}`, transform: "scale(1.03)" };
    case "peer":
      return { boxShadow: `0 0 12px ${color}55` };
    case "dim":
      return { opacity: 0.35 };
    default:
      return {};
  }
}

function deriveGlow(isSelected: boolean, isPeer: boolean, hasSelection: boolean): GlowState {
  if (isSelected) return "strong";
  if (isPeer) return "peer";
  if (hasSelection) return "dim";
  return "none";
}

function DownArrow({ id, color, dashed }: { id: string; color: string; dashed?: boolean }) {
  return (
    <svg width={14} height={28} style={{ overflow: "visible" }}>
      <defs>
        <marker id={id} viewBox="0 0 10 10" refX="10" refY="5" markerWidth="7" markerHeight="7" orient="auto">
          <path d="M0,0 L10,5 L0,10 z" fill={color} />
        </marker>
      </defs>
      <line
        x1={7}
        y1={0}
        x2={7}
        y2={24}
        stroke={color}
        strokeWidth={1.5}
        strokeDasharray={dashed ? "4,3" : undefined}
        markerEnd={`url(#${id})`}
      />
    </svg>
  );
}

function ProtocolLink({ id, label, color, dashed }: { id: string; label: string; color: string; dashed?: boolean }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
      <span style={PROTOCOL_LABEL}>{label}</span>
      <DownArrow id={id} color={color} dashed={dashed} />
    </div>
  );
}

export function AgentGraph({ agents, selected, highlightedAgent, onSelect }: Props) {
  const onlineCount = agents.filter(a => a.online).length;
  const hasSelection = selected !== null;
  const peers = peersOf(selected, agents, TOOL_NODES);

  const userGlow = deriveGlow(false, peers.has("user"), hasSelection);
  const orchestratorGlow = deriveGlow(selected?.kind === "orchestrator", peers.has("orchestrator"), hasSelection);

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8, padding: "24px 16px", fontFamily: "monospace" }}>
      {/* USER */}
      <div
        data-node="user"
        data-glow={userGlow}
        style={{
          ...NODE_CARD_BASE,
          cursor: "default",
          border: "1px solid #2a2a40",
          ...glowStyle(userGlow, "#4a9eff"),
        }}
      >
        <div style={{ fontSize: 22 }}>👤</div>
        <div style={{ color: "#aaa", marginTop: 4, fontSize: 11 }}>USER</div>
      </div>

      <ProtocolLink id="arrow-agui" label="AG-UI" color="#4a9eff" />

      {/* ORCHESTRATOR */}
      <div
        onClick={() => onSelect(selected?.kind === "orchestrator" ? null : { kind: "orchestrator" })}
        data-node="orchestrator"
        data-glow={orchestratorGlow}
        style={{
          ...NODE_CARD_BASE,
          background: "#0f3460",
          border: `1px solid ${selected?.kind === "orchestrator" ? "#80c0ff" : "#4a9eff"}`,
          color: "#4a9eff",
          ...glowStyle(orchestratorGlow, "#4a9eff"),
        }}
      >
        <div style={{ fontSize: 22 }}>🤖</div>
        <div style={{ fontSize: 11, fontWeight: "bold", marginTop: 4 }}>orchestrator</div>
        <div style={{ fontSize: 9, color: "#6aa", marginTop: 2 }}>:8000</div>
        <div style={{ fontSize: 9, color: "#555", marginTop: 4 }}>{onlineCount}/{agents.length} agents online</div>
      </div>

      {/* Two downstream branches: MCP → TOOLS, A2A → AGENTS */}
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-start", gap: 80, marginTop: 12, justifyContent: "center" }}>
        {/* MCP branch */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
          <ProtocolLink id="arrow-mcp" label="MCP" color="#888" dashed />
          <div style={CLUSTER_LABEL}>TOOLS</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: CARD_GAP, justifyContent: "center" }}>
            {TOOL_NODES.map(tool => {
              const isSelected = selected?.kind === "tool" && selected.name === tool.name;
              const isPeer = peers.has(`tool:${tool.name}`);
              const state = deriveGlow(isSelected, isPeer, hasSelection);
              return (
                <div
                  key={tool.name}
                  onClick={() => onSelect(isSelected ? null : { kind: "tool", name: tool.name })}
                  data-node={`tool-${tool.name}`}
                  data-glow={state}
                  style={{
                    ...NODE_CARD_BASE,
                    border: `1px ${isSelected ? "solid" : "dashed"} ${isSelected ? "#aaa" : "#666"}`,
                    ...glowStyle(state, "#aaaaaa"),
                  }}
                >
                  <div style={{ fontSize: 22 }}>🔧</div>
                  <div style={{ color: "#aaa", marginTop: 4, fontSize: 11 }}>{tool.name}</div>
                  <div style={{ color: "#555", fontSize: 9 }}>{tool.port}</div>
                </div>
              );
            })}
          </div>
        </div>

        {/* A2A branch */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
          <ProtocolLink id="arrow-a2a" label="A2A" color="#6a7a9a" dashed />
          <div style={CLUSTER_LABEL}>AGENTS</div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: `repeat(auto-fit, ${CARD_WIDTH}px)`,
              gap: CARD_GAP,
              justifyContent: "center",
              maxWidth: (CARD_WIDTH + CARD_GAP) * 4,
            }}
          >
            {agents.map(agent => {
              const cfg = AGENT_COLORS[agent.name as AgentKey] ?? { emoji: "🤖", color: "#aaa", label: agent.name };
              const isSelected = selected?.kind === "agent" && selected.name === agent.name;
              const isPeer = peers.has(`agent:${agent.name}`);
              const state = deriveGlow(isSelected, isPeer, hasSelection);
              const isHighlighted = highlightedAgent === agent.name;
              return (
                <div
                  key={agent.name}
                  data-agent-name={agent.name}
                  data-glow={state}
                  onClick={() => onSelect(isSelected ? null : { kind: "agent", name: agent.name as AgentKey })}
                  style={{
                    ...NODE_CARD_BASE,
                    border: `1px solid ${isSelected ? cfg.color : (agent.online ? "#1e3a1e" : "#3a1e1e")}`,
                    ...glowStyle(state, cfg.color),
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
        </div>
      </div>
    </div>
  );
}
