import { AGENT_COLORS, type AgentKey, type AgentStats } from "../../types";

const DAY_LETTERS = ["S", "M", "T", "W", "T", "F", "S"];

interface Props {
  agentKey: AgentKey;
  stats: AgentStats;
}

export function BarChart({ agentKey, stats }: Props) {
  const cfg = AGENT_COLORS[agentKey];
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
