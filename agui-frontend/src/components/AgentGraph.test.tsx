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

  it("renders TOOLS cluster with calendar-mcp and home-assistant", () => {
    render(<AgentGraph agents={AGENTS} selected={null} highlightedAgent={null} onSelect={() => {}} />);
    expect(screen.getByText("calendar-mcp")).toBeInTheDocument();
    expect(screen.getByText(":9100")).toBeInTheDocument();
    expect(screen.getByText("home-assistant")).toBeInTheDocument();
    expect(screen.getByText("lan:8123")).toBeInTheDocument();
  });

  it("renders all specialist agent names in the AGENTS cluster", () => {
    render(<AgentGraph agents={AGENTS} selected={null} highlightedAgent={null} onSelect={() => {}} />);
    expect(screen.getByText("sleep")).toBeInTheDocument();
    expect(screen.getByText("workout")).toBeInTheDocument();
    expect(screen.getByText("nutrition")).toBeInTheDocument();
  });

  it("does not glow any card when nothing is selected", () => {
    const { container } = render(<AgentGraph agents={AGENTS} selected={null} highlightedAgent={null} onSelect={() => {}} />);
    const glowAttrs = Array.from(container.querySelectorAll("[data-glow]")).map(el => el.getAttribute("data-glow"));
    expect(glowAttrs.every(v => v === "none")).toBe(true);
  });

  it("glows the selected agent strong, other agents + orchestrator as peers, tools+user dimmed", () => {
    const { container } = render(
      <AgentGraph agents={AGENTS} selected={{ kind: "agent", name: "sleep" }} highlightedAgent={null} onSelect={() => {}} />,
    );
    expect(container.querySelector('[data-agent-name="sleep"]')?.getAttribute("data-glow")).toBe("strong");
    expect(container.querySelector('[data-agent-name="workout"]')?.getAttribute("data-glow")).toBe("peer");
    expect(container.querySelector('[data-agent-name="nutrition"]')?.getAttribute("data-glow")).toBe("peer");
    expect(container.querySelector('[data-node="orchestrator"]')?.getAttribute("data-glow")).toBe("peer");
    expect(container.querySelector('[data-node="tool-calendar-mcp"]')?.getAttribute("data-glow")).toBe("dim");
    expect(container.querySelector('[data-node="user"]')?.getAttribute("data-glow")).toBe("dim");
  });

  it("glows orchestrator strong and all connected nodes as peers when orchestrator is selected", () => {
    const { container } = render(
      <AgentGraph agents={AGENTS} selected={{ kind: "orchestrator" }} highlightedAgent={null} onSelect={() => {}} />,
    );
    expect(container.querySelector('[data-node="orchestrator"]')?.getAttribute("data-glow")).toBe("strong");
    expect(container.querySelector('[data-node="user"]')?.getAttribute("data-glow")).toBe("peer");
    expect(container.querySelector('[data-node="tool-calendar-mcp"]')?.getAttribute("data-glow")).toBe("peer");
    expect(container.querySelector('[data-agent-name="sleep"]')?.getAttribute("data-glow")).toBe("peer");
    expect(container.querySelector('[data-agent-name="workout"]')?.getAttribute("data-glow")).toBe("peer");
    expect(container.querySelector('[data-agent-name="nutrition"]')?.getAttribute("data-glow")).toBe("peer");
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

  it("renders the DATA cluster with finance node", () => {
    render(<AgentGraph agents={AGENTS} selected={null} highlightedAgent={null} onSelect={() => {}} />);
    expect(screen.getByText("DATA")).toBeInTheDocument();
    expect(screen.getByText("SQL")).toBeInTheDocument();
    expect(screen.getByText("finance")).toBeInTheDocument();
    expect(screen.getByText("sql")).toBeInTheDocument();
  });

  it("calls onSelect with data selection when finance is clicked", () => {
    const onSelect = vi.fn();
    render(<AgentGraph agents={AGENTS} selected={null} highlightedAgent={null} onSelect={onSelect} />);
    screen.getByText("finance").click();
    expect(onSelect).toHaveBeenCalledWith({ kind: "data", name: "finance" });
  });

  it("highlights finance as peer when orchestrator is selected", () => {
    const { container } = render(
      <AgentGraph agents={AGENTS} selected={{ kind: "orchestrator" }} highlightedAgent={null} onSelect={() => {}} />,
    );
    expect(
      container.querySelector('[data-node="data-finance"]')?.getAttribute("data-glow"),
    ).toBe("peer");
  });
});
