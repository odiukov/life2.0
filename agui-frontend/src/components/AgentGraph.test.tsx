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
    expect(screen.getAllByText(/orchestrator/i).length).toBeGreaterThan(0);
  });

  it("renders all agent names", () => {
    render(<AgentGraph agents={AGENTS} selectedAgent={null} onSelect={() => {}} />);
    expect(screen.getByText("sleep")).toBeInTheDocument();
    expect(screen.getByText("workout")).toBeInTheDocument();
    expect(screen.getByText("nutrition")).toBeInTheDocument();
  });

  it("renders peer consult edges between sleep, workout, nutrition", () => {
    const { container } = render(<AgentGraph agents={AGENTS} selectedAgent={null} onSelect={() => {}} />);
    const peerEdges = container.querySelectorAll('path[data-peer-edge]');
    expect(peerEdges).toHaveLength(3);
    const pairs = Array.from(peerEdges).map(el => el.getAttribute("data-peer-edge"));
    expect(pairs).toContain("sleep-workout");
    expect(pairs).toContain("workout-nutrition");
    expect(pairs).toContain("sleep-nutrition");
  });

  it("renders a calendar-mcp node with port label", () => {
    render(<AgentGraph agents={AGENTS} selectedAgent={null} onSelect={() => {}} />);
    expect(screen.getByText("calendar-mcp")).toBeInTheDocument();
    expect(screen.getByText(":9100")).toBeInTheDocument();
    expect(screen.getByText("MCP")).toBeInTheDocument();
  });

  it("renders a legend describing edge styles", () => {
    render(<AgentGraph agents={AGENTS} selectedAgent={null} onSelect={() => {}} />);
    expect(screen.getByText(/peer consult/i)).toBeInTheDocument();
    expect(screen.getByText(/orchestrator.*agent/i)).toBeInTheDocument();
  });
});
