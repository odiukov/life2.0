import type { AgentInfo, Selection, StatsResponse, AgentKey } from "../types";
import { AGENT_COLORS, TOOL_NODES, DATA_NODES, peersOf } from "../types";
import { AgentCard } from "./AgentCard";
import { StatCard } from "./stats/StatCard";
import { BarChart } from "./stats/BarChart";
import { ActivityFeed } from "./stats/ActivityFeed";

interface Props {
  selected: Selection;
  agents: AgentInfo[];
  stats: StatsResponse | null;
  onClose: () => void;
}

const PANE_STYLE: React.CSSProperties = {
  width: 320,
  minWidth: 320,
  background: "#13131f",
  borderRight: "1px solid #1e1e30",
  overflowY: "auto",
  padding: 16,
  display: "flex",
  flexDirection: "column",
  gap: 14,
  fontFamily: "monospace",
  color: "#e0e0e0",
};

const HEADER_STYLE: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
};

const CLOSE_BTN_STYLE: React.CSSProperties = {
  background: "none",
  border: "none",
  color: "#555",
  cursor: "pointer",
  fontSize: 16,
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ color: "#555", fontSize: 9, textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>{title}</div>
      {children}
    </div>
  );
}

function peerLabel(id: string): { emoji: string; text: string } {
  if (id === "user") return { emoji: "👤", text: "USER" };
  if (id === "orchestrator") return { emoji: "🤖", text: "orchestrator" };
  if (id.startsWith("agent:")) {
    const name = id.slice("agent:".length);
    const cfg = AGENT_COLORS[name as AgentKey];
    return { emoji: cfg?.emoji ?? "🤖", text: name };
  }
  if (id.startsWith("tool:")) {
    return { emoji: "🔧", text: id.slice("tool:".length) };
  }
  if (id.startsWith("data:")) {
    return { emoji: "💾", text: id.slice("data:".length) };
  }
  return { emoji: "·", text: id };
}

function ConnectionsSection({ selected, agents }: { selected: Selection; agents: AgentInfo[] }) {
  const peers = peersOf(selected, agents, TOOL_NODES, DATA_NODES);
  if (peers.size === 0) return null;
  return (
    <Section title="Connections">
      <div data-section="connections" style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {Array.from(peers).map(id => {
          const { emoji, text } = peerLabel(id);
          return (
            <span
              key={id}
              data-peer-id={id}
              style={{
                background: "#1a1a2e",
                borderRadius: 10,
                padding: "3px 8px",
                fontSize: 10,
                color: "#ccc",
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
              }}
            >
              <span>{emoji}</span>
              <span>{text}</span>
            </span>
          );
        })}
      </div>
    </Section>
  );
}

export function TopologyDetailPane({ selected, agents, stats, onClose }: Props) {
  if (!selected) return null;

  if (selected.kind === "agent") {
    const agent = agents.find(a => a.name === selected.name);
    if (!agent) return null;
    const agentStats = stats?.agents[selected.name];
    return (
      <div style={PANE_STYLE}>
        <AgentCard agent={agent} onClose={onClose} />
        {agentStats && (
          <Section title="Last 7 days">
            <StatCard agentKey={selected.name} stats={agentStats} />
          </Section>
        )}
        {agentStats && (
          <Section title="Trend">
            <div style={{ background: "#1a1a2e", borderRadius: 6, padding: 10 }}>
              <BarChart agentKey={selected.name} stats={agentStats} />
            </div>
          </Section>
        )}
        <ConnectionsSection selected={selected} agents={agents} />
        {stats && (
          <ActivityFeed items={stats.activity} filterAgent={selected.name} />
        )}
      </div>
    );
  }

  if (selected.kind === "orchestrator") {
    const onlineCount = agents.filter(a => a.online).length;
    return (
      <div style={PANE_STYLE}>
        <div style={HEADER_STYLE}>
          <div style={{ fontSize: 13, fontWeight: "bold", color: "#4a9eff" }}>🧭 orchestrator-agent</div>
          <button onClick={onClose} style={CLOSE_BTN_STYLE} aria-label="close">×</button>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 11 }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "#555" }}>Port</span><span>:8000</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "#555" }}>Agents online</span>
            <span style={{ color: "#4eff9a" }}>{onlineCount} / {agents.length}</span>
          </div>
          <div style={{ color: "#888", fontSize: 10, marginTop: 4 }}>
            Routes user requests to specialist agents and MCP tools.
          </div>
        </div>
        <ConnectionsSection selected={selected} agents={agents} />
      </div>
    );
  }

  if (selected.kind === "data") {
    const meta = DATA_NODES.find(d => d.name === selected.name);
    return (
      <div style={PANE_STYLE}>
        <div style={HEADER_STYLE}>
          <div style={{ fontSize: 13, fontWeight: "bold" }}>💾 <span>{selected.name}</span></div>
          <button onClick={onClose} style={CLOSE_BTN_STYLE} aria-label="close">×</button>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 11 }}>
          {meta && (
            <>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "#555" }}>Port</span><span>{meta.port}</span>
              </div>
              <div style={{ color: "#888", fontSize: 10, marginTop: 4 }}>{meta.description}</div>
            </>
          )}
        </div>
        <ConnectionsSection selected={selected} agents={agents} />
      </div>
    );
  }

  // kind === "tool"
  const TOOL_META: Record<string, { port: string; description: string }> = {
    "calendar-mcp": { port: ":9100", description: "MCP server exposing calendar read/write tools." },
    "home-assistant": { port: "lan:8123", description: "HA native MCP server — live state (GetLiveContext) + confirm-gated Hass* mutations." },
  };
  const meta = TOOL_META[selected.name];
  return (
    <div style={PANE_STYLE}>
      <div style={HEADER_STYLE}>
        <div style={{ fontSize: 13, fontWeight: "bold" }}>🔧 <span>{selected.name}</span></div>
        <button onClick={onClose} style={CLOSE_BTN_STYLE} aria-label="close">×</button>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 11 }}>
        {meta && (
          <>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "#555" }}>Port</span><span>{meta.port}</span>
            </div>
            <div style={{ color: "#888", fontSize: 10, marginTop: 4 }}>{meta.description}</div>
          </>
        )}
      </div>
      <ConnectionsSection selected={selected} agents={agents} />
    </div>
  );
}
