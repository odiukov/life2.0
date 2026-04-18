import { AGENT_COLORS, type AgentKey, type AgentStats } from "../../types";

interface Props {
  agentKey: AgentKey;
  stats: AgentStats;
}

export function StatCard({ agentKey, stats }: Props) {
  const cfg = AGENT_COLORS[agentKey];
  const deltaStr =
    stats.delta > 0 ? `↑ ${stats.delta}` :
    stats.delta < 0 ? `↓ ${Math.abs(stats.delta)}` :
    "→ same";
  const deltaColor = stats.delta > 0 ? "#4eff9a" : stats.delta < 0 ? "#e57373" : "#888";
  return (
    <div style={{ background: "#1a1a2e", borderRadius: 6, padding: "10px 12px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <div>
        <div style={{ color: "#555", fontSize: 9, marginBottom: 2 }}>{cfg.emoji} {cfg.label} this week</div>
        <div style={{ fontSize: 20, fontWeight: "bold", color: cfg.color }}>{stats.tasks_week}</div>
      </div>
      <div style={{ fontSize: 9, color: deltaColor }}>{deltaStr}</div>
    </div>
  );
}
