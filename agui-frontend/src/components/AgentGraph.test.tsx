import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { AgentGraph } from "./AgentGraph";
import type { AgentInfo } from "../types";

const AGENTS: AgentInfo[] = [
  { name: "sleep", url: "http://agent-sleep:8001", online: true, skills: [{ id: "analyze_sleep", name: "Analyze sleep" }], description: "", tasks_today: 2 },
  { name: "workout", url: "http://agent-workout:8002", online: false, skills: [{ id: "log_workout", name: "Log workout" }], description: "", tasks_today: 0 },
  { name: "nutrition", url: "http://agent-nutrition:8003", online: true, skills: [{ id: "log_meal", name: "Log meal" }], description: "", tasks_today: 1 },
];

describe("AgentGraph", () => {
  it("renders orchestrator node", () => {
    render(<AgentGraph agents={AGENTS} selectedAgent={null} onSelect={() => {}} />);
    expect(screen.getByText(/orchestrator/i)).toBeInTheDocument();
  });

  it("renders all agent names", () => {
    render(<AgentGraph agents={AGENTS} selectedAgent={null} onSelect={() => {}} />);
    expect(screen.getByText("sleep")).toBeInTheDocument();
    expect(screen.getByText("workout")).toBeInTheDocument();
    expect(screen.getByText("nutrition")).toBeInTheDocument();
  });
});
