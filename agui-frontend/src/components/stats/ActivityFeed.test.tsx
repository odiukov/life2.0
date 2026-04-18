import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ActivityFeed } from "./ActivityFeed";
import type { ActivityItem } from "../../types";

const ITEMS: ActivityItem[] = [
  { agent: "sleep",     task_type: "analyze_sleep", message: "Slept 7.8h", created_at: "2026-04-18T06:00:00Z" },
  { agent: "workout",   task_type: "log_workout",   message: "Ran 5km",    created_at: "2026-04-18T07:00:00Z" },
  { agent: "nutrition", task_type: "log_meal",      message: "Oatmeal",    created_at: "2026-04-18T08:00:00Z" },
];

describe("ActivityFeed", () => {
  it("renders all items when no filter", () => {
    render(<ActivityFeed items={ITEMS} />);
    expect(screen.getByText("Slept 7.8h")).toBeInTheDocument();
    expect(screen.getByText("Ran 5km")).toBeInTheDocument();
    expect(screen.getByText("Oatmeal")).toBeInTheDocument();
  });

  it("filters to one agent when filterAgent is set", () => {
    render(<ActivityFeed items={ITEMS} filterAgent="workout" />);
    expect(screen.getByText("Ran 5km")).toBeInTheDocument();
    expect(screen.queryByText("Slept 7.8h")).not.toBeInTheDocument();
    expect(screen.queryByText("Oatmeal")).not.toBeInTheDocument();
  });

  it("shows 'No activity yet' when filtered list is empty", () => {
    render(<ActivityFeed items={[]} filterAgent="sleep" />);
    expect(screen.getByText(/no activity yet/i)).toBeInTheDocument();
  });
});
