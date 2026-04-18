import { useState } from "react";
import type { StatsResponse, ActivityItem, AgentStats } from "../types";
import { AGENT_COLORS, type AgentKey } from "../types";
import { StatCard } from "./stats/StatCard";

const AGENT_CONFIG = AGENT_COLORS;

const DAY_LETTERS = ["S", "M", "T", "W", "T", "F", "S"];

function BarChart({ agentKey, stats }: { agentKey: AgentKey; stats: AgentStats }) {
  const cfg = AGENT_CONFIG[agentKey];
  const daily = stats.daily ?? [];
  const maxVal = Math.max(1, ...daily);

  const today = new Date();
  const dayLabels = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(today);
    d.setDate(today.getDate() - (6 - i));
    return DAY_LETTERS[d.getDay()];
  });

  return (
    <div>
      <div style={{ color: cfg.color, fontSize: 9, marginBottom: 4 }}>{cfg.emoji} {cfg.label} (tasks/day)</div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 32 }}>
        {daily.map((val, i) => (
          <div
            key={i}
            style={{ background: cfg.color, flex: 1, height: `${Math.max(8, (val / maxVal) * 100)}%`, borderRadius: "2px 2px 0 0", opacity: 0.8 }}
          />
        ))}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", color: "#444", fontSize: 8, marginTop: 2 }}>
        {dayLabels.map((d, i) => <span key={i}>{d}</span>)}
      </div>
    </div>
  );
}

function ActivityFeed({ items }: { items: ActivityItem[] }) {
  const [hidden, setHidden] = useState(false);
  const visible = hidden ? [] : items;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <div style={{ color: "#555", fontSize: 9, textTransform: "uppercase", letterSpacing: 1 }}>Recent activity</div>
        {items.length > 0 && !hidden && (
          <button onClick={() => setHidden(true)} style={{ background: "none", border: "none", color: "#444", fontSize: 9, cursor: "pointer", padding: 0, fontFamily: "monospace" }}>
            clear
          </button>
        )}
      </div>
      {visible.length === 0 && <div style={{ color: "#444", fontSize: 10 }}>No activity yet</div>}
      {visible.map((item, i) => {
        const cfg = AGENT_CONFIG[item.agent as AgentKey] ?? AGENT_CONFIG.sleep;
        const ts = new Date(item.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        const date = new Date(item.created_at).toLocaleDateString([], { month: "short", day: "numeric" });
        return (
          <div key={i}>
            <div style={{ display: "flex", gap: 8, alignItems: "flex-start", padding: "6px 0" }}>
              <span style={{ fontSize: 13 }}>{cfg.emoji}</span>
              <div>
                <div style={{ fontSize: 10, color: "#ddd" }}>{item.message || item.task_type}</div>
                <div style={{ fontSize: 9, color: "#444" }}>{date} {ts}</div>
              </div>
            </div>
            {i < items.length - 1 && <div style={{ height: 1, background: "#1e1e30", marginLeft: 22 }} />}
          </div>
        );
      })}
    </div>
  );
}

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
