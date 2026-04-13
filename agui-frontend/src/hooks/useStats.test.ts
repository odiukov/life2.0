import { renderHook, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import { useStats } from "./useStats";
import type { StatsResponse } from "../types";

const MOCK_STATS: StatsResponse = {
  agents: {
    sleep: { tasks_week: 5, tasks_prev_week: 3, delta: 2 },
    workout: { tasks_week: 3, tasks_prev_week: 4, delta: -1 },
    nutrition: { tasks_week: 4, tasks_prev_week: 2, delta: 2 },
  },
  activity: [
    { agent: "sleep", task_type: "analyze_sleep", message: "test", created_at: "2026-04-13T08:00:00Z" },
  ],
};

describe("useStats", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MOCK_STATS),
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns null initially then fetched data", async () => {
    const { result } = renderHook(() => useStats());
    expect(result.current.data).toBeNull();
    await waitFor(() => expect(result.current.data).not.toBeNull());
    expect(result.current.data?.agents.sleep.tasks_week).toBe(5);
    expect(result.current.data?.activity).toHaveLength(1);
  });

  it("sets error on fetch failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network error")));
    const { result } = renderHook(() => useStats());
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error).toBe("network error");
  });
});
