import { useState } from "react";
import { AGENT_COLORS, type AgentKey, type ActivityItem } from "../../types";

interface Props {
  items: ActivityItem[];
  filterAgent?: AgentKey;
}

export function ActivityFeed({ items, filterAgent }: Props) {
  const [hidden, setHidden] = useState(false);
  const filtered = filterAgent ? items.filter(i => i.agent === filterAgent) : items;
  const visible = hidden ? [] : filtered;
  const title = filterAgent ? `Recent activity — ${filterAgent}` : "Recent activity";

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <div style={{ color: "#555", fontSize: 9, textTransform: "uppercase", letterSpacing: 1 }}>{title}</div>
        {filtered.length > 0 && !hidden && (
          <button onClick={() => setHidden(true)} style={{ background: "none", border: "none", color: "#444", fontSize: 9, cursor: "pointer", padding: 0, fontFamily: "monospace" }}>
            clear
          </button>
        )}
      </div>
      {visible.length === 0 && <div style={{ color: "#444", fontSize: 10 }}>No activity yet</div>}
      {visible.map((item, i) => {
        const cfg = AGENT_COLORS[item.agent as AgentKey] ?? { emoji: "🤖", label: item.agent, color: "#aaa" };
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
            {i < visible.length - 1 && <div style={{ height: 1, background: "#1e1e30", marginLeft: 22 }} />}
          </div>
        );
      })}
    </div>
  );
}
