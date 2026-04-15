import type { ToolCall } from "../types";

interface Props {
  currentStep?: string;
  activeAgent?: "sleep" | "workout" | "nutrition" | null;
  toolCalls?: ToolCall[];
}

export function AgentStatusBar({ currentStep, activeAgent, toolCalls }: Props) {
  const running = (toolCalls ?? []).filter((t) => t.status === "running");
  const hasActivity =
    running.length > 0 ||
    (currentStep !== undefined && currentStep !== "idle" && currentStep !== "");
  if (!hasActivity) return null;
  return (
    <div
      role="status"
      style={{
        padding: "6px 10px",
        fontSize: 13,
        background: "#eef2ff",
        borderTop: "1px solid #c7d2fe",
      }}
    >
      <span>🔄 {currentStep ?? "working"}</span>
      {activeAgent && (
        <span style={{ marginLeft: 8, opacity: 0.7 }}>· agent: {activeAgent}</span>
      )}
      {running.length > 0 && (
        <span style={{ marginLeft: 8, opacity: 0.7 }}>
          · {running.length} running
        </span>
      )}
    </div>
  );
}
