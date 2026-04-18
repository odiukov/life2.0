import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { AgentCard } from "./AgentCard";
import type { AgentInfo } from "../types";

const BASE: AgentInfo = {
  name: "sleep",
  url: "http://agent-sleep:8001",
  online: true,
  skills: [{ id: "log_sleep", name: "Log sleep" }, { id: "analyze_sleep", name: "Analyze sleep" }],
  description: "Sleep tracker",
  tasks_today: 3,
};

describe("AgentCard", () => {
  it("renders skill ids as chips under a Skills heading", () => {
    render(<AgentCard agent={BASE} onClose={() => {}} />);
    expect(screen.getByText(/skills/i)).toBeInTheDocument();
    expect(screen.getByText("log_sleep")).toBeInTheDocument();
    expect(screen.getByText("analyze_sleep")).toBeInTheDocument();
  });

  it("does not crash when skills is missing from the payload", () => {
    const broken = { ...BASE, skills: undefined as unknown as AgentInfo["skills"] };
    expect(() => render(<AgentCard agent={broken} onClose={() => {}} />)).not.toThrow();
  });

  it("does not crash when skills is not an array", () => {
    const broken = { ...BASE, skills: { streaming: true } as unknown as AgentInfo["skills"] };
    expect(() => render(<AgentCard agent={broken} onClose={() => {}} />)).not.toThrow();
  });

  it("hides the Skills section when skills is empty or missing", () => {
    const { rerender } = render(<AgentCard agent={{ ...BASE, skills: [] }} onClose={() => {}} />);
    expect(screen.queryByText(/^skills$/i)).not.toBeInTheDocument();
    rerender(<AgentCard agent={{ ...BASE, skills: undefined as unknown as AgentInfo["skills"] }} onClose={() => {}} />);
    expect(screen.queryByText(/^skills$/i)).not.toBeInTheDocument();
  });
});
