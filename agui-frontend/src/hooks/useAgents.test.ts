import { renderHook, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import { useAgents } from "./useAgents";

const MOCK_AGENTS = {
  agents: [
    { name: "sleep", url: "http://agent-sleep:8001", online: true, skills: [{ id: "analyze_sleep", name: "Analyze sleep" }], description: "", tasks_today: 3 },
    { name: "workout", url: "http://agent-workout:8002", online: false, skills: [{ id: "log_workout", name: "Log workout" }], description: "", tasks_today: 0 },
  ],
};

describe("useAgents", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MOCK_AGENTS),
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns agent list with online status", async () => {
    const { result } = renderHook(() => useAgents());
    await waitFor(() => expect(result.current.agents).toHaveLength(2));
    expect(result.current.agents[0].name).toBe("sleep");
    expect(result.current.agents[0].online).toBe(true);
    expect(result.current.agents[1].online).toBe(false);
  });
});
