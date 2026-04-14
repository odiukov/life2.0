import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { DashboardPanel } from "./DashboardPanel";
import type { HealthSummary } from "../types";

const SUMMARY: HealthSummary = {
  body: { weight_kg: 79.6, body_fat_pct: 26.5, lean_mass_kg: 58.4, bmi: 24.1 },
  sleep: { duration_hours: 7.5, score: 85, hrv: 45, deep_hours: 1.5, rem_hours: 1.2, light_hours: 4.8 },
  daily: { steps: 8234, calories_active: 450, body_battery_max: 85, resting_hr: 58, stress_avg: 35 },
  trends: {
    sleep_hours: [7, 6.5, 8, 7.5, 7, 6, 7.5],
    workout_minutes: [0, 60, 0, 45, 0, 90, 0],
    nutrition_calories: [1800, 2100, 1950, 2000, 1750, 2200, 1900],
  },
  recommendation: {
    agent: "sleep",
    text: "Your sleep score has improved. Try maintaining a consistent bedtime.",
    created_at: "2026-04-13T08:00:00Z",
  },
};

describe("DashboardPanel", () => {
  it("renders health metrics", () => {
    render(<DashboardPanel summary={SUMMARY} />);
    expect(screen.getByText(/79.6/)).toBeInTheDocument();
    expect(screen.getByText(/7.5h/)).toBeInTheDocument();
  });

  it("renders loading state when summary is null", () => {
    render(<DashboardPanel summary={null} />);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });
});
