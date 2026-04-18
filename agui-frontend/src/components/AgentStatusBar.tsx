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
        padding: "6px 12px",
        fontSize: 11,
        fontFamily: "monospace",
        background: "#13131f",
        color: "#9ca3af",
        borderTop: "1px solid #1e1e30",
      }}
    >
      <span style={{ color: "#4a9eff" }}>🔄</span>{" "}
      <span>{currentStep ?? "working"}</span>
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
