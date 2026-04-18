import type { StatsResponse, AgentStats } from "../types";
import { AGENT_COLORS, type AgentKey } from "../types";
import { StatCard } from "./stats/StatCard";
import { BarChart } from "./stats/BarChart";
import { ActivityFeed } from "./stats/ActivityFeed";

const AGENT_CONFIG = AGENT_COLORS;

interface Props {
  stats: StatsResponse | null;
}

export function AgentStatsPanel({ stats }: Props) {
  if (!stats) {
    return (
      <div style={{ padding: 16, color: "#555", fontSize: 11, fontFamily: "monospace" }}>Loading...</div>
    );
  }

  const agents: AgentKey[] = ["sleep", "workout", "nutrition"];

  return (
    <div style={{
      width: 240,
      minWidth: 240,
      background: "#13131f",
      borderRight: "1px solid #1e1e30",
      overflowY: "auto",
      padding: 16,
      display: "flex",
      flexDirection: "column",
      gap: 14,
      fontFamily: "monospace",
    }}>
      <div>
        <div style={{ color: "#555", fontSize: 9, textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>Last 7 days</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {agents.map(a => <StatCard key={a} agentKey={a} stats={stats.agents[a]} />)}
        </div>
      </div>

      <div>
        <div style={{ color: "#555", fontSize: 9, textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>Trends</div>
        <div style={{ background: "#1a1a2e", borderRadius: 6, padding: 10, display: "flex", flexDirection: "column", gap: 10 }}>
          {agents.map(a => <BarChart key={a} agentKey={a} stats={stats.agents[a]} />)}
        </div>
      </div>

      <ActivityFeed items={stats.activity} />
    </div>
  );
}
