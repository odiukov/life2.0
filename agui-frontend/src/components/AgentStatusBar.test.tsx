import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AgentStatusBar } from "./AgentStatusBar";
import type { ToolCall } from "../types";

const running: ToolCall = {
  id: "t1", name: "ask_workout_agent", skill: "log_workout",
  status: "running", startedAt: "2026-04-15T10:00:00Z",
};
const done: ToolCall = { ...running, id: "t2", status: "done", endedAt: "2026-04-15T10:00:03Z" };

describe("AgentStatusBar", () => {
  it("renders nothing when idle and no running calls", () => {
    const { container } = render(
      <AgentStatusBar currentStep="idle" activeAgent={null} toolCalls={[done]} />
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows currentStep and active agent when running", () => {
    render(
      <AgentStatusBar
        currentStep="querying workout (log_workout)"
        activeAgent="workout"
        toolCalls={[running]}
      />
    );
    expect(screen.getByText(/querying workout/i)).toBeInTheDocument();
    expect(screen.getAllByText(/workout/i).length).toBeGreaterThan(0);
  });

  it("renders nothing when state is all undefined", () => {
    const { container } = render(<AgentStatusBar />);
    expect(container.firstChild).toBeNull();
  });
});
