import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { DashboardPanel } from "./DashboardPanel";
import type { StatsResponse } from "../types";

const STATS: StatsResponse = {
  agents: {
    sleep: { tasks_week: 5, tasks_prev_week: 3, delta: 2, daily: [1,1,1,1,1,0,0] },
    workout: { tasks_week: 3, tasks_prev_week: 4, delta: -1, daily: [0,0,1,1,1,0,0] },
    nutrition: { tasks_week: 4, tasks_prev_week: 2, delta: 2, daily: [1,1,1,1,0,0,0] },
  },
  activity: [
    { agent: "sleep", task_type: "analyze_sleep", message: "slept 7h", created_at: "2026-04-13T08:00:00Z" },
  ],
};

describe("DashboardPanel", () => {
  it("renders stat cards for each agent", () => {
    render(<DashboardPanel stats={STATS} />);
    expect(screen.getAllByText(/sleep/i).length).toBeGreaterThan(0);
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText(/slept 7h/i)).toBeInTheDocument();
  });

  it("renders loading state when stats is null", () => {
    render(<DashboardPanel stats={null} />);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });
});
