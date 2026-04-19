import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { TopologyDetailPane } from "./TopologyDetailPane";
import type { AgentInfo, StatsResponse } from "../types";

const AGENTS: AgentInfo[] = [
  { name: "sleep",     url: "http://agent-sleep:8001",     online: true,  skills: [{ id: "analyze_sleep", name: "Analyze sleep" }], description: "Sleep tracker",     tasks_today: 2 },
  { name: "workout",   url: "http://agent-workout:8002",   online: true,  skills: [], description: "Workout tracker",   tasks_today: 1 },
  { name: "nutrition", url: "http://agent-nutrition:8003", online: false, skills: [], description: "Nutrition tracker", tasks_today: 0 },
];

const STATS: StatsResponse = {
  agents: {
    sleep:     { tasks_week: 7, tasks_prev_week: 5, delta: 2, daily: [1,1,1,1,1,1,1] },
    workout:   { tasks_week: 3, tasks_prev_week: 3, delta: 0, daily: [0,1,0,1,0,1,0] },
    nutrition: { tasks_week: 0, tasks_prev_week: 0, delta: 0, daily: [0,0,0,0,0,0,0] },
  },
  activity: [
    { agent: "sleep",     task_type: "analyze_sleep", message: "Slept 7.8h", created_at: "2026-04-18T06:00:00Z" },
    { agent: "workout",   task_type: "log_workout",   message: "Ran 5km",    created_at: "2026-04-18T07:00:00Z" },
  ],
};

describe("TopologyDetailPane", () => {
  it("renders nothing when selected is null", () => {
    const { container } = render(
      <TopologyDetailPane selected={null} agents={AGENTS} stats={STATS} onClose={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders specialist-agent detail with stats and filtered activity", () => {
    render(
      <TopologyDetailPane
        selected={{ kind: "agent", name: "sleep" }}
        agents={AGENTS}
        stats={STATS}
        onClose={() => {}}
      />,
    );
    expect(screen.getByText("sleep-agent")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument(); // tasks_week
    expect(screen.getByText("Slept 7.8h")).toBeInTheDocument();
    expect(screen.queryByText("Ran 5km")).not.toBeInTheDocument();
  });

  it("renders orchestrator detail with online count", () => {
    render(
      <TopologyDetailPane
        selected={{ kind: "orchestrator" }}
        agents={AGENTS}
        stats={STATS}
        onClose={() => {}}
      />,
    );
    expect(screen.getByText(/orchestrator/i)).toBeInTheDocument();
    expect(screen.getByText(/2\s*\/\s*3/)).toBeInTheDocument();
  });

  it("renders tool detail with name and port", () => {
    render(
      <TopologyDetailPane
        selected={{ kind: "tool", name: "calendar-mcp" }}
        agents={AGENTS}
        stats={STATS}
        onClose={() => {}}
      />,
    );
    expect(screen.getByText("calendar-mcp")).toBeInTheDocument();
    expect(screen.getByText(":9100")).toBeInTheDocument();
  });

  it("calls onClose when close button is clicked", () => {
    const onClose = vi.fn();
    render(
      <TopologyDetailPane
        selected={{ kind: "orchestrator" }}
        agents={AGENTS}
        stats={STATS}
        onClose={onClose}
      />,
    );
    screen.getByRole("button", { name: /×|close/i }).click();
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("lists A2A peers in Connections section when an agent is selected", () => {
    const { container } = render(
      <TopologyDetailPane
        selected={{ kind: "agent", name: "sleep" }}
        agents={AGENTS}
        stats={STATS}
        onClose={() => {}}
      />,
    );
    const section = container.querySelector('[data-section="connections"]');
    expect(section).not.toBeNull();
    const peerIds = Array.from(section!.querySelectorAll("[data-peer-id]")).map(el => el.getAttribute("data-peer-id"));
    expect(peerIds).toContain("orchestrator");
    expect(peerIds).toContain("agent:workout");
    expect(peerIds).toContain("agent:nutrition");
    expect(peerIds).not.toContain("agent:sleep");
    expect(peerIds).not.toContain("user");
  });

  it("lists all reachable nodes in Connections section when orchestrator is selected", () => {
    const { container } = render(
      <TopologyDetailPane
        selected={{ kind: "orchestrator" }}
        agents={AGENTS}
        stats={STATS}
        onClose={() => {}}
      />,
    );
    const section = container.querySelector('[data-section="connections"]');
    expect(section).not.toBeNull();
    const peerIds = Array.from(section!.querySelectorAll("[data-peer-id]")).map(el => el.getAttribute("data-peer-id"));
    expect(peerIds).toContain("user");
    expect(peerIds).toContain("tool:calendar-mcp");
    expect(peerIds).toContain("agent:sleep");
    expect(peerIds).toContain("agent:workout");
    expect(peerIds).toContain("agent:nutrition");
  });

  it("renders data-node detail pane with name/port/description", () => {
    render(
      <TopologyDetailPane
        selected={{ kind: "data", name: "payoneer-finance" }}
        agents={[]}
        stats={null}
        onClose={() => {}}
      />,
    );
    expect(screen.getByText(/payoneer-finance/)).toBeInTheDocument();
    expect(screen.getByText("csv/sql")).toBeInTheDocument();
    expect(screen.getByText(/CSV upload/)).toBeInTheDocument();
  });
});
