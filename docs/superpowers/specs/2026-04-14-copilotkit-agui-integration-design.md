# CopilotKit + AG-UI Integration Design

**Date:** 2026-04-14  
**Status:** Approved

## Overview

Replace the custom `ChatPanel` component with CopilotKit's `<CopilotChat>` UI and add agentic actions that allow the AI to manipulate the dashboard directly. The backend gets a new `/copilotkit` endpoint alongside the existing `/chat/stream` (which stays untouched as a fallback).

## Architecture

```
Browser
  └─ <CopilotKit runtimeUrl="/copilotkit">
       ├─ <CopilotChat>          (replaces ChatPanel)
       └─ useCopilotAction(...)  (in Dashboard + AgentCard)

Nginx /copilotkit → orchestrator:8000/copilotkit  (new)
Nginx /chat/stream → orchestrator:8000/chat/stream (unchanged)

orchestrator/app/main.py
  └─ /copilotkit endpoint  (new, via copilotkit Python SDK)
       └─ calls existing classify_intent() + agent routing logic
```

## Backend Changes

**File:** `orchestrator/app/main.py`

Add CopilotKit SDK setup and endpoint:

```python
from copilotkit import CopilotKitSDK, Action
from copilotkit.integrations.fastapi import add_fastapi_endpoint

sdk = CopilotKitSDK(
    actions=[
        Action(name="refresh_health_data", description="Refresh health metrics on the dashboard"),
        Action(name="navigate_to_agents", description="Switch to the Agents tab"),
        Action(name="highlight_agent", description="Highlight a specific agent in the graph (sleep/workout/nutrition)"),
        Action(name="show_metric_detail", description="Expand a specific metric card (sleep, weight, steps)"),
        Action(name="trigger_sync", description="Start data synchronization"),
        Action(name="trigger_briefing", description="Generate and send the daily health briefing via Telegram"),
        Action(name="ask_agent", description="Send a pre-filled question to a specific agent"),
    ]
)
add_fastapi_endpoint(app, sdk, "/copilotkit")
```

The action handler logic internally reuses `classify_intent()` and the existing agent routing — no duplication.

**File:** `orchestrator/requirements.txt`

```
copilotkit>=0.1
```

## Frontend Changes

### 1. Upgrade CopilotKit

```
@copilotkit/react-core: ^1.3.0 → ^1.8
@copilotkit/react-ui:   ^1.3.0 → ^1.8
```

### 2. Provider in App.tsx / main.tsx

```tsx
import { CopilotKit } from "@copilotkit/react-core";

<CopilotKit runtimeUrl="/copilotkit">
  <App />
</CopilotKit>
```

### 3. Replace ChatPanel with CopilotChat

```tsx
import { CopilotChat } from "@copilotkit/react-ui";
import "@copilotkit/react-ui/styles.css";

<CopilotChat
  instructions="You are a personal health assistant with access to sleep, workout, and nutrition data."
/>
```

`ChatPanel.tsx` is deleted.

### 4. Register Actions in Dashboard.tsx

```tsx
import { useCopilotAction } from "@copilotkit/react-core";
import { useNavigate } from "react-router-dom";

// Refresh health metrics
useCopilotAction({
  name: "refresh_health_data",
  description: "Refresh health metrics on the dashboard",
  handler: () => healthSummary.refresh(),
});

// Navigate to Agents tab
useCopilotAction({
  name: "navigate_to_agents",
  description: "Switch to the Agents tab",
  handler: () => navigate("/agents"),
});

// Highlight agent in graph (registered in AgentGraph.tsx or Agents page)
useCopilotAction({
  name: "highlight_agent",
  description: "Highlight a specific agent in the graph",
  parameters: [{ name: "agent", type: "string", description: "sleep | workout | nutrition" }],
  handler: ({ agent }) => setHighlightedAgent(agent),
});

// Show metric detail card
useCopilotAction({
  name: "show_metric_detail",
  description: "Expand a specific metric card",
  parameters: [{ name: "metric", type: "string", description: "sleep | weight | steps | body_battery" }],
  handler: ({ metric }) => setExpandedMetric(metric),
});

// Trigger sync
useCopilotAction({
  name: "trigger_sync",
  description: "Start data synchronization",
  handler: async () => {
    await fetch("/chat/stream", { method: "POST", body: JSON.stringify({ messages: [{ role: "user", content: "sync" }] }) });
    healthSummary.refresh();
  },
});

// Trigger daily briefing
useCopilotAction({
  name: "trigger_briefing",
  description: "Generate and send the daily health briefing via Telegram",
  handler: async () => {
    await fetch("/briefing", { method: "POST" });
  },
});

// Ask agent (pre-fills and submits a question)
useCopilotAction({
  name: "ask_agent",
  description: "Send a pre-filled question to a specific agent",
  parameters: [
    { name: "agent", type: "string", description: "sleep | workout | nutrition" },
    { name: "question", type: "string", description: "The question to ask" },
  ],
  handler: ({ question }) => {
    // CopilotChat exposes appendMessage or similar API
    // Fallback: navigate to chat with pre-filled input
  },
});
```

## Nginx

Add to nginx config:

```nginx
location /copilotkit {
    proxy_pass http://orchestrator:8000/copilotkit;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
}
```

## Error Handling

- **Backend unavailable:** CopilotKit renders a built-in error state in the chat UI
- **Action failure:** `useCopilotAction` `onError` callback logs to console; no user-visible crash
- **Rollback:** `/chat/stream` remains intact; restore `ChatPanel` from git if needed

## Out of Scope

- Styling customization of CopilotChat (using defaults, option B)
- `useCopilotReadable` for context injection (can be added later)
- Message history persistence across sessions

## Files Changed

| File | Change |
|------|--------|
| `orchestrator/requirements.txt` | Add `copilotkit>=0.1` |
| `orchestrator/app/main.py` | Add SDK + `/copilotkit` endpoint |
| `orchestrator/nginx.conf` | Add `/copilotkit` proxy location |
| `agui-frontend/package.json` | Upgrade CopilotKit to `^1.8` |
| `agui-frontend/src/main.tsx` or `App.tsx` | Wrap with `<CopilotKit>` provider |
| `agui-frontend/src/components/ChatPanel.tsx` | Delete |
| `agui-frontend/src/pages/Dashboard.tsx` | Replace `<ChatPanel>` with `<CopilotChat>`, register 5 actions |
| `agui-frontend/src/pages/Agents.tsx` | Register `highlight_agent` action |
