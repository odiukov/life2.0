import type { StatsResponse, ActivityItem, AgentStats } from "../types";

const AGENT_CONFIG = {
  sleep:     { emoji: "😴", label: "Sleep",     color: "#4a9eff" },
  workout:   { emoji: "💪", label: "Workout",   color: "#4eff9a" },
  nutrition: { emoji: "🥗", label: "Nutrition", color: "#ffb74a" },
} as const;

type AgentKey = keyof typeof AGENT_CONFIG;

function StatCard({ agentKey, stats }: { agentKey: AgentKey; stats: AgentStats }) {
  const cfg = AGENT_CONFIG[agentKey];
  const deltaStr = stats.delta > 0 ? `↑ ${stats.delta}` : stats.delta < 0 ? `↓ ${Math.abs(stats.delta)}` : "→ same";
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

function BarChart({ agentKey, stats }: { agentKey: AgentKey; stats: AgentStats }) {
  const cfg = AGENT_CONFIG[agentKey];
  const maxVal = Math.max(1, stats.tasks_week);
  const bars = Array.from({ length: 7 }, (_, i) => {
    const val = i === 6 ? Math.ceil(stats.tasks_week / 7) : Math.floor(stats.tasks_week / 7);
    return Math.min(1, val / maxVal);
  });
  const days = ["M", "T", "W", "T", "F", "S", "S"];
  return (
    <div>
      <div style={{ color: cfg.color, fontSize: 9, marginBottom: 4 }}>{cfg.emoji} {cfg.label} (tasks/day est.)</div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 32 }}>
        {bars.map((h, i) => (
          <div
            key={i}
            style={{ background: cfg.color, flex: 1, height: `${Math.max(8, h * 100)}%`, borderRadius: "2px 2px 0 0", opacity: 0.8 }}
          />
        ))}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", color: "#444", fontSize: 8, marginTop: 2 }}>
        {days.map((d, i) => <span key={i}>{d}</span>)}
      </div>
    </div>
  );
}

function ActivityFeed({ items }: { items: ActivityItem[] }) {
  return (
    <div>
      <div style={{ color: "#555", fontSize: 9, textTransform: "uppercase", letterSpacing: 1, marginBottom: 6 }}>Recent activity</div>
      {items.length === 0 && <div style={{ color: "#444", fontSize: 10 }}>No activity yet</div>}
      {items.map((item, i) => {
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

export function DashboardPanel({ stats }: Props) {
  if (!stats) {
    return (
      <div style={{ padding: 16, color: "#555", fontSize: 11, fontFamily: "monospace" }}>Loading...</div>
    );
  }

  const agents: AgentKey[] = ["sleep", "workout", "nutrition"];

  return (
    <div style={{
      width: 260,
      minWidth: 260,
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
