import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ChatPanel } from "./ChatPanel";

vi.mock("@copilotkit/react-ui", () => ({
  CopilotChat: ({ labels }: { labels: { title: string } }) => (
    <div data-testid="copilot-chat">{labels.title}</div>
  ),
}));

describe("ChatPanel", () => {
  it("renders CopilotChat with life-agents title", () => {
    render(<ChatPanel />);
    expect(screen.getByTestId("copilot-chat")).toBeInTheDocument();
    expect(screen.getByText("life-agents")).toBeInTheDocument();
  });
});
