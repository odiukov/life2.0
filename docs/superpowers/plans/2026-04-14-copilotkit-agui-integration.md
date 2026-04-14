# CopilotKit + AG-UI Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the custom `ChatPanel` with CopilotKit's `<CopilotChat>` UI and add 7 agentic actions that allow the AI to manipulate the dashboard directly.

**Architecture:** A new `/copilotkit` FastAPI endpoint wraps the existing agent routing (sleep/workout/nutrition) using the `copilotkit` Python SDK and `langchain-anthropic`. The frontend is upgraded to CopilotKit v1.8, wrapped in a `<CopilotKit>` provider, and `ChatPanel` is replaced with `<CopilotChat>`. Four frontend-only actions (`refresh_health_data`, `navigate_to_agents`, `highlight_agent`, `show_metric_detail`) are registered with `useCopilotAction`. Three backend actions (`call_health_agent`, `run_sync`, `run_briefing`) let the LLM call specialist agents and services.

**Tech Stack:** FastAPI, `copilotkit` Python SDK, `langchain-anthropic`, Claude Sonnet 4.6, React 18, CopilotKit v1.8, `@copilotkit/react-core`, `@copilotkit/react-ui`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `orchestrator/requirements.txt` | Modify | Add `copilotkit`, `langchain-anthropic` |
| `orchestrator/app/main.py` | Modify | Add CopilotKit SDK setup + `/copilotkit` endpoint |
| `agui-frontend/nginx.conf` | Modify | Add `/copilotkit` proxy location |
| `agui-frontend/package.json` | Modify | Upgrade CopilotKit to `^1.8` |
| `agui-frontend/src/main.tsx` | Modify | Wrap app in `<CopilotKit>` provider |
| `agui-frontend/src/pages/DashboardPage.tsx` | Modify | Replace `<ChatPanel>` with `<CopilotChat>`, register 4 actions |
| `agui-frontend/src/components/DashboardPanel.tsx` | Modify | Accept `expandedMetric` prop for visual highlight |
| `agui-frontend/src/pages/AgentsPage.tsx` | Modify | Read `highlighted` from router state, add visual highlight |
| `agui-frontend/src/components/ChatPanel.tsx` | Delete | Replaced by `<CopilotChat>` |
| `agui-frontend/src/components/ChatPanel.test.tsx` | Delete | No longer needed |

---

## Task 1: Add Python packages and create `/copilotkit` endpoint

**Files:**
- Modify: `orchestrator/requirements.txt`
- Modify: `orchestrator/app/main.py`
- Test: `tests/test_copilotkit_endpoint.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_copilotkit_endpoint.py`:

```python
import pytest
import httpx
from unittest.mock import patch, AsyncMock
from orchestrator.app.main import app


@pytest.mark.asyncio
async def test_copilotkit_endpoint_is_registered():
    """POST /copilotkit should exist (not 404)."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/copilotkit", json={})
    assert response.status_code != 404
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /Users/oleksandr/Documents/life-agents
pip install pytest pytest-asyncio httpx
pytest tests/test_copilotkit_endpoint.py -v
```

Expected: FAIL — `AssertionError: assert 404 != 404` (endpoint doesn't exist yet)

- [ ] **Step 3: Add packages to requirements.txt**

In `orchestrator/requirements.txt`, append:

```
copilotkit>=0.1
langchain-anthropic>=0.3
```

- [ ] **Step 4: Add CopilotKit SDK setup to main.py**

At the top of `orchestrator/app/main.py`, after the existing imports, add:

```python
from copilotkit import CopilotKitSDK, Action
from copilotkit.integrations.fastapi import add_fastapi_endpoint
from langchain_anthropic import ChatAnthropic
```

After the `app = FastAPI(...)` and `app.add_middleware(...)` block, add:

```python
# ---------------------------------------------------------------------------
# CopilotKit SDK
# ---------------------------------------------------------------------------

async def _call_health_agent_handler(message: str, agent: str, **kwargs) -> str:
    """Call a specialist agent (sleep | workout | nutrition) and return its response."""
    agent_url = get_agent_url(agent)
    if not agent_url:
        return f"Agent '{agent}' is currently unavailable."
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                f"{agent_url}/tasks",
                json={
                    "id": str(uuid.uuid4()),
                    "task": AGENT_DEFAULT_TASK.get(agent, f"analyze_{agent}"),
                    "params": {
                        "message": message,
                        "peer_agents": _build_peer_agents(agent),
                    },
                },
            )
            resp.raise_for_status()
            return _artifact_text(resp.json())
    except Exception as e:
        return f"Error calling {agent} agent: {str(e)}"


async def _run_sync_handler(**kwargs) -> str:
    """Trigger data synchronization and return a status message."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post("http://sync-service:8080/sync")
            resp.raise_for_status()
            data = resp.json()
            text = f"Sync complete: {data['synced']} records synced, {data['skipped']} skipped."
            if data.get("errors"):
                text += f" Errors: {'; '.join(data['errors'][:3])}"
            return text
    except Exception as e:
        return f"Sync failed: {str(e)}"


async def _run_briefing_handler(**kwargs) -> str:
    """Generate and send the daily health briefing via Telegram."""
    try:
        await run_briefing(get_registry())
        return "Daily health briefing generated and sent via Telegram."
    except Exception as e:
        return f"Briefing failed: {str(e)}"


# ANTHROPIC_API_KEY is loaded from .env.auth by docker-compose.
# CopilotKit SDK picks it up automatically when langchain-anthropic is installed.
# If it doesn't (e.g., defaults to OpenAI), add: llm=ChatAnthropic(model="claude-sonnet-4-6")
# and check CopilotKit docs for the correct kwarg name.
_copilotkit_sdk = CopilotKitSDK(
    actions=[
        Action(
            name="call_health_agent",
            description=(
                "Call a specialized health agent to analyze the user's data. "
                "Use agent='sleep' for sleep questions, 'workout' for exercise, "
                "'nutrition' for diet and food."
            ),
            parameters=[
                {
                    "name": "message",
                    "type": "string",
                    "description": "The user's question or request",
                },
                {
                    "name": "agent",
                    "type": "string",
                    "description": "Which agent to call: sleep | workout | nutrition",
                },
            ],
            handler=_call_health_agent_handler,
        ),
        Action(
            name="run_sync",
            description="Synchronize health data from external sources (Garmin, Yazio).",
            parameters=[],
            handler=_run_sync_handler,
        ),
        Action(
            name="run_briefing",
            description="Generate and send the daily health briefing via Telegram.",
            parameters=[],
            handler=_run_briefing_handler,
        ),
    ],
)

add_fastapi_endpoint(app, _copilotkit_sdk, "/copilotkit")
```

- [ ] **Step 5: Install packages and run test**

```bash
cd /Users/oleksandr/Documents/life-agents/orchestrator
pip install copilotkit langchain-anthropic
pytest ../tests/test_copilotkit_endpoint.py -v
```

Expected: PASS — `assert 200 != 404` (or some non-404 response)

- [ ] **Step 6: Commit**

```bash
git add orchestrator/requirements.txt orchestrator/app/main.py tests/test_copilotkit_endpoint.py
git commit -m "feat: add CopilotKit Python SDK endpoint to orchestrator"
```

---

## Task 2: Add `/copilotkit` nginx proxy location

**Files:**
- Modify: `agui-frontend/nginx.conf`

- [ ] **Step 1: Add the proxy location**

In `agui-frontend/nginx.conf`, insert before the `# SPA fallback` comment:

```nginx
location /copilotkit {
    proxy_pass http://orchestrator:8000;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 300s;
    proxy_set_header Connection '';
    proxy_http_version 1.1;
    proxy_set_header X-Real-IP $remote_addr;
}

location /briefing {
    proxy_pass http://orchestrator:8000;
}
```

The full file after the change should look like:

```nginx
server {
    listen 80;

    # SSE: disable buffering so events flow immediately
    location /chat/ {
        proxy_pass http://orchestrator:8000;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /stats {
        proxy_pass http://orchestrator:8000;
    }

    location /health-summary {
        proxy_pass http://orchestrator:8000;
    }

    location /agents {
        proxy_pass http://orchestrator:8000;
    }

    location /health {
        proxy_pass http://orchestrator:8000;
    }

    location /activity {
        proxy_pass http://orchestrator:8000;
    }

    location /sync {
        proxy_pass http://sync-service:8080;
    }

    location /copilotkit {
        proxy_pass http://orchestrator:8000;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /briefing {
        proxy_pass http://orchestrator:8000;
    }

    # SPA fallback
    location / {
        root /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add agui-frontend/nginx.conf
git commit -m "feat: add /copilotkit and /briefing nginx proxy locations"
```

---

## Task 3: Upgrade CopilotKit frontend packages

**Files:**
- Modify: `agui-frontend/package.json`

- [ ] **Step 1: Update package versions**

In `agui-frontend/package.json`, change the CopilotKit versions in `dependencies`:

```json
"@copilotkit/react-core": "^1.8.0",
"@copilotkit/react-ui": "^1.8.0",
```

- [ ] **Step 2: Install updated packages**

```bash
cd /Users/oleksandr/Documents/life-agents/agui-frontend
npm install
```

Expected: packages install without errors.

- [ ] **Step 3: Run existing tests to verify no breakage**

```bash
npm test
```

Expected: all existing tests pass.

- [ ] **Step 4: Commit**

```bash
git add agui-frontend/package.json agui-frontend/package-lock.json
git commit -m "chore: upgrade CopilotKit to v1.8"
```

---

## Task 4: Add `<CopilotKit>` provider in main.tsx

**Files:**
- Modify: `agui-frontend/src/main.tsx`

- [ ] **Step 1: Update main.tsx**

Replace the full content of `agui-frontend/src/main.tsx` with:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { CopilotKit } from "@copilotkit/react-core";
import "@copilotkit/react-ui/styles.css";
import "./index.css";
import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <CopilotKit runtimeUrl="/copilotkit">
      <App />
    </CopilotKit>
  </React.StrictMode>
);
```

- [ ] **Step 2: Run tests**

```bash
cd /Users/oleksandr/Documents/life-agents/agui-frontend
npm test
```

Expected: all tests pass (provider doesn't affect existing component tests).

- [ ] **Step 3: Commit**

```bash
git add agui-frontend/src/main.tsx
git commit -m "feat: wrap app in CopilotKit provider"
```

---

## Task 5: Replace ChatPanel with CopilotChat + register dashboard actions

**Files:**
- Delete: `agui-frontend/src/components/ChatPanel.tsx`
- Delete: `agui-frontend/src/components/ChatPanel.test.tsx`
- Modify: `agui-frontend/src/pages/DashboardPage.tsx`

- [ ] **Step 1: Delete ChatPanel files**

```bash
rm agui-frontend/src/components/ChatPanel.tsx
rm agui-frontend/src/components/ChatPanel.test.tsx
```

- [ ] **Step 2: Replace DashboardPage.tsx**

Replace the full content of `agui-frontend/src/pages/DashboardPage.tsx` with:

```tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCopilotAction } from "@copilotkit/react-core";
import { CopilotChat } from "@copilotkit/react-ui";
import { DashboardPanel } from "../components/DashboardPanel";
import { useHealthSummary } from "../hooks/useHealthSummary";

export default function DashboardPage() {
  const { data, refresh } = useHealthSummary();
  const navigate = useNavigate();
  const [expandedMetric, setExpandedMetric] = useState<string | null>(null);

  useCopilotAction({
    name: "refresh_health_data",
    description: "Refresh the health metrics displayed on the dashboard",
    parameters: [],
    handler: () => {
      refresh();
    },
  });

  useCopilotAction({
    name: "navigate_to_agents",
    description: "Switch to the Agents tab to show agent topology and stats",
    parameters: [],
    handler: () => {
      navigate("/agents");
    },
  });

  useCopilotAction({
    name: "highlight_agent",
    description: "Navigate to the Agents tab and visually highlight a specific agent",
    parameters: [
      {
        name: "agent",
        type: "string",
        description: "Which agent to highlight: sleep | workout | nutrition",
      },
    ],
    handler: ({ agent }: { agent: string }) => {
      navigate("/agents", { state: { highlighted: agent } });
    },
  });

  useCopilotAction({
    name: "show_metric_detail",
    description: "Visually highlight a specific health metric card on the dashboard",
    parameters: [
      {
        name: "metric",
        type: "string",
        description: "Which metric to highlight: sleep | weight | steps | body_battery",
      },
    ],
    handler: ({ metric }: { metric: string }) => {
      setExpandedMetric(metric);
      setTimeout(() => setExpandedMetric(null), 4000);
    },
  });

  return (
    <div style={{ display: "flex", height: "calc(100vh - 41px)", overflow: "hidden" }}>
      <DashboardPanel summary={data} expandedMetric={expandedMetric} />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <CopilotChat
          instructions={
            "You are a personal health assistant. The user tracks sleep, workouts, and nutrition. " +
            "Use call_health_agent to fetch analysis from specialist agents before responding. " +
            "Use run_sync when the user wants to synchronize data. " +
            "Use run_briefing to generate and send the daily health briefing. " +
            "Use refresh_health_data after a sync to update the dashboard. " +
            "Use highlight_agent to draw the user's attention to a specific agent. " +
            "Use show_metric_detail to highlight a specific metric card."
          }
          labels={{
            title: "life-agents",
            initial: "Ask about your sleep, workouts, or nutrition.",
          }}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Run tests**

```bash
cd /Users/oleksandr/Documents/life-agents/agui-frontend
npm test
```

Expected: ChatPanel tests are gone (files deleted), remaining tests pass.

- [ ] **Step 4: Commit**

```bash
git add agui-frontend/src/pages/DashboardPage.tsx
git rm agui-frontend/src/components/ChatPanel.tsx agui-frontend/src/components/ChatPanel.test.tsx
git commit -m "feat: replace ChatPanel with CopilotChat, register dashboard actions"
```

---

## Task 6: Add `expandedMetric` highlight support to DashboardPanel

**Files:**
- Modify: `agui-frontend/src/components/DashboardPanel.tsx`

- [ ] **Step 1: Read the current DashboardPanel.tsx**

Read the file to understand the current prop interface and metric card structure before editing.

- [ ] **Step 2: Add `expandedMetric` prop**

In `agui-frontend/src/components/DashboardPanel.tsx`, update the props interface. Find the existing interface definition (e.g., `interface DashboardPanelProps`) and add the new prop:

```tsx
interface DashboardPanelProps {
  summary: HealthSummary | null;
  expandedMetric?: string | null;
}
```

Update the function signature:

```tsx
export function DashboardPanel({ summary, expandedMetric }: DashboardPanelProps) {
```

- [ ] **Step 3: Add highlight helper and apply to metric sections**

Add this helper just inside the component function, before the return:

```tsx
const highlight = (key: string): React.CSSProperties =>
  expandedMetric === key
    ? { outline: "2px solid #4a9eff", outlineOffset: "2px", borderRadius: "4px", transition: "outline 0.2s" }
    : {};
```

Find each metric section's outer `<div>` and spread the highlight style. The metric keys to use:
- Sleep section → `style={{ ...existingStyle, ...highlight("sleep") }}`
- Weight/body section → `style={{ ...existingStyle, ...highlight("weight") }}`
- Steps/daily section → `style={{ ...existingStyle, ...highlight("steps") }}`
- Body battery section → `style={{ ...existingStyle, ...highlight("body_battery") }}`

> Note: Read the file to find the exact section divs before editing. Match the existing inline style pattern — use spread `{ ...existing, ...highlight("key") }`.

- [ ] **Step 4: Run tests**

```bash
cd /Users/oleksandr/Documents/life-agents/agui-frontend
npm test
```

Expected: DashboardPanel tests pass (DashboardPanel.test.tsx verifies rendering).

- [ ] **Step 5: Commit**

```bash
git add agui-frontend/src/components/DashboardPanel.tsx
git commit -m "feat: add expandedMetric highlight to DashboardPanel"
```

---

## Task 7: Add `highlight_agent` visual highlight to AgentsPage

**Files:**
- Modify: `agui-frontend/src/pages/AgentsPage.tsx`

- [ ] **Step 1: Update AgentsPage.tsx**

Replace the full content of `agui-frontend/src/pages/AgentsPage.tsx` with:

```tsx
import { useState } from "react";
import { useLocation } from "react-router-dom";
import { AgentGraph } from "../components/AgentGraph";
import { AgentCard } from "../components/AgentCard";
import { AgentStatsPanel } from "../components/AgentStatsPanel";
import { useAgents } from "../hooks/useAgents";
import { useStats } from "../hooks/useStats";
import type { AgentInfo } from "../types";

export default function AgentsPage() {
  const { agents, loading, error } = useAgents();
  const { data: stats } = useStats();
  const [selected, setSelected] = useState<string | null>(null);
  const location = useLocation();
  const highlighted: string | null = (location.state as { highlighted?: string } | null)?.highlighted ?? null;

  const selectedAgent: AgentInfo | undefined = agents.find(a => a.name === selected);

  if (loading) {
    return <div style={{ padding: 32, color: "#555", fontFamily: "monospace" }}>Discovering agents...</div>;
  }

  if (error) {
    return <div style={{ padding: 32, color: "#e57373", fontFamily: "monospace" }}>Error: {error}</div>;
  }

  return (
    <div style={{ display: "flex", height: "calc(100vh - 41px)", overflow: "hidden" }}>
      <AgentStatsPanel stats={stats} />
      <div style={{ flex: 1, overflowY: "auto", padding: 32, display: "flex", flexDirection: "column", alignItems: "center", gap: 24 }}>
        <h2 style={{ color: "#e0e0e0", fontFamily: "monospace", fontWeight: "normal", margin: 0 }}>
          Agent Topology
        </h2>
        <AgentGraph
          agents={agents}
          selectedAgent={selected}
          highlightedAgent={highlighted}
          onSelect={setSelected}
        />
        {selectedAgent && (
          <AgentCard agent={selectedAgent} onClose={() => setSelected(null)} />
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Update AgentGraph to accept `highlightedAgent` prop**

Read `agui-frontend/src/components/AgentGraph.tsx` first to understand the current interface.

Then update the props interface to add:
```tsx
highlightedAgent?: string | null;
```

And the function signature:
```tsx
export function AgentGraph({ agents, selectedAgent, highlightedAgent, onSelect }: AgentGraphProps) {
```

For each agent node rendered in the graph, add a highlight ring when `highlightedAgent` matches the agent name. Find the agent node div/element and add a conditional style:

```tsx
style={{
  // ...existing node styles...
  ...(highlightedAgent === agent.name
    ? { outline: "2px solid #4a9eff", outlineOffset: "3px", animation: "pulse-ring 2s ease-in-out 3" }
    : {}),
}}
```

> Read AgentGraph.tsx before editing — find the exact element that renders each agent bubble and add the highlight style there.

- [ ] **Step 3: Run tests**

```bash
cd /Users/oleksandr/Documents/life-agents/agui-frontend
npm test
```

Expected: AgentGraph tests pass.

- [ ] **Step 4: Commit**

```bash
git add agui-frontend/src/pages/AgentsPage.tsx agui-frontend/src/components/AgentGraph.tsx
git commit -m "feat: highlight agent in graph via CopilotKit action"
```

---

## Task 8: Verify full integration end-to-end

- [ ] **Step 1: Build and start services**

```bash
cd /Users/oleksandr/Documents/life-agents
docker compose up --build -d
```

- [ ] **Step 2: Check orchestrator logs for CopilotKit startup**

```bash
docker compose logs orchestrator | grep -i "copilotkit\|error" | head -20
```

Expected: no import errors, copilotkit endpoint registered.

- [ ] **Step 3: Test CopilotChat renders**

Open `http://localhost:3000` in browser.
Expected: Chat panel on the right side of Dashboard uses CopilotKit's default UI (no longer the custom dark panel).

- [ ] **Step 4: Test a basic chat message**

Type "How did I sleep last night?" in the chat.
Expected: CopilotChat shows a streaming response from the sleep agent.

- [ ] **Step 5: Test an action**

Type "Show me my nutrition agent" in the chat.
Expected: App navigates to Agents tab and the nutrition agent node is highlighted with a blue outline.

- [ ] **Step 6: Run all frontend tests one final time**

```bash
cd agui-frontend && npm test
```

Expected: all tests pass.

- [ ] **Step 7: Final commit**

```bash
git add -A
git commit -m "feat: CopilotKit + AG-UI integration complete"
```
