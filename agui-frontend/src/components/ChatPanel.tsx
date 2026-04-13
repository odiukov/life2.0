import { CopilotChat } from "@copilotkit/react-ui";

export function ChatPanel() {
  return (
    <div style={{
      flex: 1,
      display: "flex",
      flexDirection: "column",
      background: "#0d0d1a",
      fontFamily: "monospace",
      overflow: "hidden",
    }}>
      <CopilotChat
        labels={{
          title: "life-agents",
          initial: "Ask about your sleep, workouts, or nutrition.",
          placeholder: "Ask your agents...",
        }}
        instructions="You are routing user messages to specialised health agents. Be concise and direct."
      />
    </div>
  );
}
