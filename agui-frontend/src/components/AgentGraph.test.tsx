import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { AgentGraph } from "./AgentGraph";
import type { AgentInfo } from "../types";

const AGENTS: AgentInfo[] = [
  { name: "sleep",     url: "http://agent-sleep:8001",     online: true,  skills: [{ id: "analyze_sleep", name: "Analyze sleep" }], description: "", tasks_today: 2 },
  { name: "workout",   url: "http://agent-workout:8002",   online: false, skills: [{ id: "log_workout", name: "Log workout" }],     description: "", tasks_today: 0 },
  { name: "nutrition", url: "http://agent-nutrition:8003", online: true,  skills: [{ id: "log_meal", name: "Log meal" }],           description: "", tasks_today: 1 },
];

describe("AgentGraph (topology)", () => {
  it("renders the USER node", () => {
    render(<AgentGraph agents={AGENTS} selected={null} highlightedAgent={null} onSelect={() => {}} />);
    expect(screen.getByText(/^USER$/)).toBeInTheDocument();
  });

  it("renders the AGENT orchestrator node", () => {
    render(<AgentGraph agents={AGENTS} selected={null} highlightedAgent={null} onSelect={() => {}} />);
    expect(screen.getAllByText(/orchestrator/i).length).toBeGreaterThan(0);
  });

  it("renders all protocol labels (AG-UI, MCP, A2A)", () => {
    render(<AgentGraph agents={AGENTS} selected={null} highlightedAgent={null} onSelect={() => {}} />);
    expect(screen.getByText("AG-UI")).toBeInTheDocument();
    expect(screen.getByText("MCP")).toBeInTheDocument();
    expect(screen.getByText("A2A")).toBeInTheDocument();
  });

  it("renders TOOLS cluster with calendar-mcp", () => {
    render(<AgentGraph agents={AGENTS} selected={null} highlightedAgent={null} onSelect={() => {}} />);
    expect(screen.getByText("calendar-mcp")).toBeInTheDocument();
    expect(screen.getByText(":9100")).toBeInTheDocument();
  });

  it("renders all specialist agent names in the AGENTS cluster", () => {
    render(<AgentGraph agents={AGENTS} selected={null} highlightedAgent={null} onSelect={() => {}} />);
    expect(screen.getByText("sleep")).toBeInTheDocument();
    expect(screen.getByText("workout")).toBeInTheDocument();
    expect(screen.getByText("nutrition")).toBeInTheDocument();
  });

  it("renders three A2A peer edges between all specialist pairs", () => {
    const { container } = render(<AgentGraph agents={AGENTS} selected={null} highlightedAgent={null} onSelect={() => {}} />);
    const peerEdges = container.querySelectorAll("path[data-peer-edge]");
    expect(peerEdges).toHaveLength(3);
    const pairs = Array.from(peerEdges).map(el => el.getAttribute("data-peer-edge"));
    expect(pairs).toContain("sleep-workout");
    expect(pairs).toContain("workout-nutrition");
    expect(pairs).toContain("sleep-nutrition");
  });

  it("calls onSelect with agent selection when a specialist card is clicked", () => {
    const onSelect = vi.fn();
    render(<AgentGraph agents={AGENTS} selected={null} highlightedAgent={null} onSelect={onSelect} />);
    screen.getByText("sleep").click();
    expect(onSelect).toHaveBeenCalledWith({ kind: "agent", name: "sleep" });
  });

  it("calls onSelect with orchestrator when the AGENT node is clicked", () => {
    const onSelect = vi.fn();
    render(<AgentGraph agents={AGENTS} selected={null} highlightedAgent={null} onSelect={onSelect} />);
    screen.getAllByText(/orchestrator/i)[0].click();
    expect(onSelect).toHaveBeenCalledWith({ kind: "orchestrator" });
  });

  it("calls onSelect with tool when calendar-mcp is clicked", () => {
    const onSelect = vi.fn();
    render(<AgentGraph agents={AGENTS} selected={null} highlightedAgent={null} onSelect={onSelect} />);
    screen.getByText("calendar-mcp").click();
    expect(onSelect).toHaveBeenCalledWith({ kind: "tool", name: "calendar-mcp" });
  });

  it("applies highlighted outline to matching agent card", () => {
    const { container } = render(<AgentGraph agents={AGENTS} selected={null} highlightedAgent="workout" onSelect={() => {}} />);
    const workoutCard = container.querySelector('[data-agent-name="workout"]') as HTMLElement;
    expect(workoutCard).not.toBeNull();
    expect(workoutCard.style.outline).toMatch(/#4a9eff/);
  });
});
