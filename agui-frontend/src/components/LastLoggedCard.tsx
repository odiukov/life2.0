import type { LogEntry } from "../types";

interface Props {
  entry?: LogEntry | null;
}

const FRESH_MS = 30_000;

export function LastLoggedCard({ entry }: Props) {
  if (!entry) return null;
  const age = Date.now() - new Date(entry.timestamp).getTime();
  if (age > FRESH_MS || age < 0) return null;
  return (
    <div
      role="status"
      style={{
        position: "absolute",
        top: 16,
        right: 16,
        padding: "10px 14px",
        background: "#ecfdf5",
        border: "1px solid #a7f3d0",
        borderRadius: 8,
        fontSize: 13,
        boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
        zIndex: 10,
      }}
    >
      <div style={{ fontWeight: 600 }}>
        ✅ {entry.agent} logged
      </div>
      <div style={{ opacity: 0.8, marginTop: 2 }}>{entry.summary}</div>
    </div>
  );
}
