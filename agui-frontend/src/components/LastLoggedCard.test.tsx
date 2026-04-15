import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LastLoggedCard } from "./LastLoggedCard";

describe("LastLoggedCard", () => {
  it("renders nothing when entry is null", () => {
    const { container } = render(<LastLoggedCard entry={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when entry is undefined", () => {
    const { container } = render(<LastLoggedCard entry={undefined} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders summary and agent for fresh entry", () => {
    const fresh = new Date().toISOString();
    render(
      <LastLoggedCard
        entry={{ agent: "workout", skill: "log_workout", summary: "30 min run", timestamp: fresh }}
      />
    );
    expect(screen.getByText(/30 min run/)).toBeInTheDocument();
    expect(screen.getByText(/workout/)).toBeInTheDocument();
  });

  it("renders nothing for stale entry older than 30s", () => {
    const stale = new Date(Date.now() - 60_000).toISOString();
    const { container } = render(
      <LastLoggedCard
        entry={{ agent: "sleep", skill: "log_sleep", summary: "slept 8h", timestamp: stale }}
      />
    );
    expect(container.firstChild).toBeNull();
  });
});
