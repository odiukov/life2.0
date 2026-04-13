# AG-UI Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a React + CopilotKit web frontend (Dashboard + Chat + Agents tab) and wire up two new orchestrator endpoints (`/chat/stream` SSE, `/stats`) that power it.

**Architecture:** nginx-served Vite+React app in Docker proxies all API calls to the orchestrator. The orchestrator gains a streaming `/chat/stream` endpoint (AG-UI SSE protocol, CopilotKit-compatible) and a `/stats` endpoint (task counts + activity feed from Postgres). Telegram bot is untouched.

**Tech Stack:** Python/FastAPI (asyncpg, SSE via `StreamingResponse`), React 18, TypeScript, CopilotKit 1.3+, Vite 5, nginx, Docker multi-stage build.

> **Note on stats data:** Agents currently write to the `tasks` table (not `health_logs`). The `/stats` endpoint queries `tasks` for per-agent interaction counts. If agents are later updated to write structured records to `health_logs`, the stats endpoint can be upgraded without frontend changes.

---

## File Map

### Orchestrator (modify existing)

| File | Change |
|---|---|
| `orchestrator/requirements.txt` | Add `asyncpg>=0.29` |
| `orchestrator/app/db.py` | New — asyncpg pool + stats queries |
| `orchestrator/app/registry.py` | Extend `list_agents()` to return full card + live health + tasks_today |
| `orchestrator/app/main.py` | Add CORS, `/stats`, `/chat/stream`; update `/agents` response |

### Frontend (all new)

| File | Purpose |
|---|---|
| `agui-frontend/package.json` | Dependencies |
| `agui-frontend/vite.config.ts` | Vite config |
| `agui-frontend/index.html` | HTML entry point |
| `agui-frontend/src/main.tsx` | React root |
| `agui-frontend/src/App.tsx` | Router + CopilotKit provider |
| `agui-frontend/src/types.ts` | Shared TS interfaces |
| `agui-frontend/src/hooks/useStats.ts` | GET /stats, polls every 60s |
| `agui-frontend/src/hooks/useAgents.ts` | GET /agents, polls every 10s |
| `agui-frontend/src/components/DashboardPanel.tsx` | Stats cards + bar charts + activity feed |
| `agui-frontend/src/components/ChatPanel.tsx` | CopilotKit chat wrapper |
| `agui-frontend/src/components/AgentGraph.tsx` | SVG node graph: orchestrator → agents |
| `agui-frontend/src/components/AgentCard.tsx` | Per-agent detail panel |
| `agui-frontend/src/pages/DashboardPage.tsx` | DashboardPanel + ChatPanel layout |
| `agui-frontend/src/pages/AgentsPage.tsx` | AgentGraph + AgentCard layout |

### Docker (modify existing + new)

| File | Change |
|---|---|
| `agui-frontend/Dockerfile` | New — two-stage node build → nginx |
| `agui-frontend/nginx.conf` | New — SPA + proxy rules |
| `docker-compose.yml` | Add `agui-frontend` service |

### Tests

| File | What it tests |
|---|---|
| `tests/test_orchestrator_stats.py` | New — `/stats` endpoint |
| `tests/test_orchestrator_stream.py` | New — `/chat/stream` SSE events |
| `agui-frontend/src/hooks/useStats.test.ts` | New — useStats hook |
| `agui-frontend/src/hooks/useAgents.test.ts` | New — useAgents hook |

---

## Task 1: Orchestrator DB module

**Files:**
- Modify: `orchestrator/requirements.txt`
- Create: `orchestrator/app/db.py`

- [ ] **Step 1: Add asyncpg to orchestrator requirements**

`orchestrator/requirements.txt`:
```
fastapi>=0.111
uvicorn[standard]>=0.29
httpx>=0.27
asyncpg>=0.29
```

- [ ] **Step 2: Write failing test for get_stats**

`tests/test_orchestrator_stats.py`:
```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_stats_endpoint_shape():
    """GET /stats returns the expected JSON shape."""
    mock_pool = AsyncMock()
    mock_pool.fetch = AsyncMock(return_value=[])
    mock_pool.fetchrow = AsyncMock(return_value=None)

    with patch("orchestrator.app.db.get_pool", return_value=mock_pool):
        from orchestrator.app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert "agents" in body
    assert "activity" in body
    assert "sleep" in body["agents"]
    assert "workout" in body["agents"]
    assert "nutrition" in body["agents"]
    for agent in body["agents"].values():
        assert "tasks_week" in agent
        assert "tasks_prev_week" in agent
        assert "delta" in agent
```

- [ ] **Step 3: Run test to confirm it fails**

```bash
cd /Users/oleksandr/Documents/life-agents
pytest tests/test_orchestrator_stats.py -v
```
Expected: `ImportError` or `ModuleNotFoundError` — `orchestrator.app.db` doesn't exist yet.

- [ ] **Step 4: Create `orchestrator/app/db.py`**

```python
import asyncpg
import json
import os
from datetime import datetime, timezone, timedelta

_pool: asyncpg.Pool | None = None


async def _set_json_codec(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(os.environ["POSTGRES_DSN"], init=_set_json_codec)
    return _pool


async def get_stats() -> dict:
    """Return per-agent task counts (this week vs prev week) and last 10 tasks as activity feed."""
    pool = await get_pool()
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    agents = ["sleep", "workout", "nutrition"]
    agent_stats = {}
    for agent in agents:
        this_week = await pool.fetchrow(
            "SELECT COUNT(*) as cnt FROM tasks WHERE agent=$1 AND created_at >= $2",
            agent, week_ago
        )
        prev_week = await pool.fetchrow(
            "SELECT COUNT(*) as cnt FROM tasks WHERE agent=$1 AND created_at >= $2 AND created_at < $3",
            agent, two_weeks_ago, week_ago
        )
        tw = int(this_week["cnt"]) if this_week else 0
        pw = int(prev_week["cnt"]) if prev_week else 0
        agent_stats[agent] = {"tasks_week": tw, "tasks_prev_week": pw, "delta": tw - pw}

    activity_rows = await pool.fetch(
        "SELECT agent, task_type, input, created_at FROM tasks "
        "ORDER BY created_at DESC LIMIT 10"
    )
    activity = [
        {
            "agent": r["agent"],
            "task_type": r["task_type"],
            "message": (r["input"] or {}).get("message", "")[:80],
            "created_at": r["created_at"].isoformat(),
        }
        for r in activity_rows
    ]

    return {"agents": agent_stats, "activity": activity}


async def get_tasks_today(agent: str) -> int:
    """Count tasks for an agent since midnight UTC today."""
    pool = await get_pool()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM tasks WHERE agent=$1 AND created_at >= $2",
        agent, today_start
    )
    return int(row["cnt"]) if row else 0
```

- [ ] **Step 5: Run test again**

```bash
pytest tests/test_orchestrator_stats.py -v
```
Expected: still fails because `/stats` endpoint doesn't exist in `main.py` yet. That's fine — we wire it in Task 2.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/requirements.txt orchestrator/app/db.py tests/test_orchestrator_stats.py
git commit -m "feat: add orchestrator db module for stats queries"
```

---

## Task 2: Extend `/agents` + add `/stats` to orchestrator

**Files:**
- Modify: `orchestrator/app/registry.py`
- Modify: `orchestrator/app/main.py`

- [ ] **Step 1: Write failing test for extended /agents**

Add to `tests/test_orchestrator_stats.py` (append after existing test):
```python
@pytest.mark.asyncio
async def test_agents_endpoint_returns_full_info():
    """GET /agents returns name, url, online, capabilities, tasks_today."""
    with patch("orchestrator.app.db.get_tasks_today", new=AsyncMock(return_value=3)):
        with patch("orchestrator.app.registry._registry", {
            "sleep": {
                "url": "http://agent-sleep:8001",
                "card": {"name": "sleep-agent", "capabilities": ["analyze_sleep"]},
                "online": True,
            }
        }):
            from orchestrator.app.main import app
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/agents")
    assert resp.status_code == 200
    agents = resp.json()["agents"]
    assert len(agents) == 1
    assert agents[0]["name"] == "sleep"
    assert agents[0]["online"] is True
    assert "capabilities" in agents[0]
    assert "tasks_today" in agents[0]
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/test_orchestrator_stats.py::test_agents_endpoint_returns_full_info -v
```
Expected: FAIL — `/agents` returns `{"agents": ["sleep"]}` (list of strings), not the expected shape.

- [ ] **Step 3: Update `orchestrator/app/registry.py`**

Replace entire file:
```python
import httpx
import os
import logging

from .router import INTENT_KEYWORDS

logger = logging.getLogger(__name__)

_registry: dict[str, dict] = {}


async def discover_agents() -> None:
    """Query all configured agent URLs for their Agent Cards."""
    agent_urls = os.environ.get("AGENT_URLS", "").split(",")

    for url in agent_urls:
        url = url.strip()
        if not url:
            continue
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{url}/.well-known/agent.json")
                resp.raise_for_status()
                card = resp.json()
                agent_name = card["name"].replace("-agent", "")
                if agent_name not in INTENT_KEYWORDS:
                    logger.warning(
                        f"Agent '{card['name']}' produces key '{agent_name}' "
                        f"which is not in known intents {list(INTENT_KEYWORDS.keys())}. "
                        f"It may not be routable by the classifier."
                    )
                _registry[agent_name] = {"url": url, "card": card, "online": True}
                logger.info(f"Discovered agent: {agent_name} at {url}")
        except Exception as e:
            logger.warning(f"Could not discover agent at {url}: {e}")


async def check_agent_health(agent_name: str) -> bool:
    """Ping agent's /health endpoint. Returns True if healthy."""
    entry = _registry.get(agent_name)
    if not entry:
        return False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{entry['url']}/health")
            return resp.status_code == 200
    except Exception:
        return False


def get_agent_url(agent_name: str) -> str | None:
    entry = _registry.get(agent_name)
    return entry["url"] if entry else None


def list_agents() -> list[str]:
    return list(_registry.keys())


def get_registry() -> dict[str, dict]:
    return _registry
```

- [ ] **Step 4: Update `orchestrator/app/main.py`**

Replace entire file:
```python
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
from pydantic import BaseModel
import httpx
import uuid
import asyncio
import json

from .registry import discover_agents, get_agent_url, list_agents, check_agent_health, get_registry
from .router import classify_intent
from .db import get_stats, get_tasks_today


AGENT_DEFAULT_TASK: dict[str, str] = {
    "sleep": "analyze_sleep",
    "workout": "analyze_workout",
    "nutrition": "analyze_nutrition",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await discover_agents()
    yield


app = FastAPI(title="Orchestrator", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    params: dict = {}


class StreamChatRequest(BaseModel):
    threadId: str = ""
    runId: str = ""
    messages: list[dict] = []
    actions: list = []
    extensions: dict = {}
    forward_props: dict = {}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _split_chunks(text: str, size: int = 5) -> list[str]:
    words = text.split()
    chunks = []
    for i in range(0, len(words), size):
        chunk = " ".join(words[i:i + size])
        if i + size < len(words):
            chunk += " "
        chunks.append(chunk)
    return chunks if chunks else [text]


@app.post("/chat")
async def chat(req: ChatRequest):
    agent_name = classify_intent(req.message)
    agent_url = get_agent_url(agent_name)

    if not agent_url:
        raise HTTPException(
            status_code=503,
            detail=f"Agent '{agent_name}' is not available. Available: {list_agents()}"
        )

    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            resp = await client.post(
                f"{agent_url}/tasks",
                json={"task": AGENT_DEFAULT_TASK.get(agent_name, f"analyze_{agent_name}"), "params": {"message": req.message}},
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Agent '{agent_name}' error: {e.response.text[:500]}",
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Could not reach agent '{agent_name}': {str(e)}",
            )


@app.post("/chat/stream")
async def chat_stream(req: StreamChatRequest):
    # Extract last user message from CopilotKit message list
    user_messages = [m for m in req.messages if m.get("role") == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")
    message = user_messages[-1].get("content", "")

    thread_id = req.threadId or str(uuid.uuid4())
    run_id = req.runId or str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    agent_name = classify_intent(message)
    agent_url = get_agent_url(agent_name)

    async def event_stream():
        yield _sse({"type": "RunStarted", "threadId": thread_id, "runId": run_id})
        yield _sse({"type": "TextMessageStart", "messageId": message_id, "role": "assistant"})

        if not agent_url:
            error_text = f"Agent '{agent_name}' is not available."
            yield _sse({"type": "TextMessageContent", "messageId": message_id, "delta": error_text})
            yield _sse({"type": "TextMessageEnd", "messageId": message_id})
            yield _sse({"type": "RunFinished", "threadId": thread_id, "runId": run_id})
            return

        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(
                    f"{agent_url}/tasks",
                    json={"task": AGENT_DEFAULT_TASK.get(agent_name, f"analyze_{agent_name}"), "params": {"message": message}},
                )
                resp.raise_for_status()
                output = resp.json().get("output", "")
        except Exception as e:
            output = f"Error contacting agent: {str(e)}"

        for chunk in _split_chunks(output, size=5):
            yield _sse({"type": "TextMessageContent", "messageId": message_id, "delta": chunk})
            await asyncio.sleep(0.02)

        yield _sse({"type": "TextMessageEnd", "messageId": message_id})
        yield _sse({"type": "RunFinished", "threadId": thread_id, "runId": run_id})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/stats")
async def stats():
    return await get_stats()


@app.get("/agents")
async def agents():
    registry = get_registry()
    result = []
    for name, entry in registry.items():
        online = await check_agent_health(name)
        tasks_today = await get_tasks_today(name)
        card = entry.get("card", {})
        result.append({
            "name": name,
            "url": entry["url"],
            "online": online,
            "capabilities": card.get("capabilities", []),
            "description": card.get("description", ""),
            "tasks_today": tasks_today,
        })
    return {"agents": result}


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Run all orchestrator tests**

```bash
pytest tests/test_orchestrator_stats.py -v
```
Expected: both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/app/registry.py orchestrator/app/main.py tests/test_orchestrator_stats.py
git commit -m "feat: extend /agents, add /stats and /chat/stream to orchestrator"
```

---

## Task 3: Test `/chat/stream` SSE events

**Files:**
- Create: `tests/test_orchestrator_stream.py`

- [ ] **Step 1: Write SSE stream tests**

`tests/test_orchestrator_stream.py`:
```python
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport


def parse_sse(raw: str) -> list[dict]:
    """Parse text/event-stream response into list of event dicts."""
    events = []
    for line in raw.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


@pytest.mark.asyncio
async def test_chat_stream_emits_agui_events():
    """POST /chat/stream emits RunStarted → TextMessageContent → RunFinished."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"status": "completed", "output": "Sleep better tonight."})

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("orchestrator.app.main.get_agent_url", return_value="http://agent-sleep:8001"):
        with patch("orchestrator.app.main.classify_intent", return_value="sleep"):
            with patch("httpx.AsyncClient", return_value=mock_client):
                from orchestrator.app.main import app
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    resp = await client.post("/chat/stream", json={
                        "threadId": "t1",
                        "runId": "r1",
                        "messages": [{"role": "user", "content": "How was my sleep?"}],
                        "actions": [],
                    })

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    events = parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert types[0] == "RunStarted"
    assert types[-1] == "RunFinished"
    assert "TextMessageStart" in types
    assert "TextMessageEnd" in types
    content_events = [e for e in events if e["type"] == "TextMessageContent"]
    assert len(content_events) > 0
    full_text = "".join(e["delta"] for e in content_events)
    assert "Sleep better tonight." in full_text


@pytest.mark.asyncio
async def test_chat_stream_no_user_message_returns_400():
    from orchestrator.app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/chat/stream", json={
            "messages": [],
        })
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_orchestrator_stream.py -v
```
Expected: both PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_orchestrator_stream.py
git commit -m "test: add /chat/stream SSE event tests"
```

---

## Task 4: Frontend scaffold

**Files:**
- Create: `agui-frontend/package.json`
- Create: `agui-frontend/vite.config.ts`
- Create: `agui-frontend/index.html`
- Create: `agui-frontend/tsconfig.json`
- Create: `agui-frontend/src/main.tsx`
- Create: `agui-frontend/src/App.tsx`
- Create: `agui-frontend/src/types.ts`

- [ ] **Step 1: Create `agui-frontend/package.json`**

```json
{
  "name": "agui-frontend",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "@copilotkit/react-core": "^1.3.0",
    "@copilotkit/react-ui": "^1.3.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.23.1"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.4.2",
    "@testing-library/react": "^15.0.7",
    "@testing-library/user-event": "^14.5.2",
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "jsdom": "^24.1.0",
    "typescript": "^5.4.5",
    "vite": "^5.3.1",
    "vitest": "^1.6.0"
  }
}
```

- [ ] **Step 2: Create `agui-frontend/vite.config.ts`**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test-setup.ts",
  },
});
```

- [ ] **Step 3: Create `agui-frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Create `agui-frontend/src/test-setup.ts`**

```typescript
import "@testing-library/jest-dom";
```

- [ ] **Step 5: Create `agui-frontend/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>life-agents</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 6: Create `agui-frontend/src/types.ts`**

```typescript
export interface AgentStats {
  tasks_week: number;
  tasks_prev_week: number;
  delta: number;
}

export interface ActivityItem {
  agent: "sleep" | "workout" | "nutrition";
  task_type: string;
  message: string;
  created_at: string;
}

export interface StatsResponse {
  agents: {
    sleep: AgentStats;
    workout: AgentStats;
    nutrition: AgentStats;
  };
  activity: ActivityItem[];
}

export interface AgentInfo {
  name: string;
  url: string;
  online: boolean;
  capabilities: string[];
  description: string;
  tasks_today: number;
}

export interface AgentsResponse {
  agents: AgentInfo[];
}
```

- [ ] **Step 7: Create `agui-frontend/src/index.css`**

```css
:root {
  --copilot-kit-primary-color: #4a9eff;
  --copilot-kit-background-color: #0d0d1a;
  --copilot-kit-secondary-color: #13131f;
  --copilot-kit-font-family: monospace;
}

body {
  margin: 0;
  background: #0d0d1a;
}
```

- [ ] **Step 8: Create `agui-frontend/src/main.tsx`**

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import "./index.css";
import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

- [ ] **Step 9: Create `agui-frontend/src/App.tsx`**

```tsx
import { CopilotKit } from "@copilotkit/react-core";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import DashboardPage from "./pages/DashboardPage";
import AgentsPage from "./pages/AgentsPage";
import "@copilotkit/react-ui/styles.css";

const NAV_STYLE: React.CSSProperties = {
  display: "flex",
  gap: "0",
  background: "#13131f",
  borderBottom: "1px solid #1e1e30",
  padding: "0 16px",
};

const LINK_STYLE: React.CSSProperties = {
  padding: "10px 16px",
  fontSize: "12px",
  color: "#666",
  textDecoration: "none",
  fontFamily: "monospace",
};

const ACTIVE_STYLE: React.CSSProperties = {
  ...LINK_STYLE,
  color: "#4a9eff",
  borderBottom: "2px solid #4a9eff",
};

export default function App() {
  return (
    <CopilotKit runtimeUrl="/chat/stream">
      <BrowserRouter>
        <div style={{ background: "#0d0d1a", minHeight: "100vh", color: "#e0e0e0" }}>
          <nav style={NAV_STYLE}>
            <NavLink
              to="/"
              end
              style={({ isActive }) => (isActive ? ACTIVE_STYLE : LINK_STYLE)}
            >
              Dashboard
            </NavLink>
            <NavLink
              to="/agents"
              style={({ isActive }) => (isActive ? ACTIVE_STYLE : LINK_STYLE)}
            >
              Agents
            </NavLink>
          </nav>
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/agents" element={<AgentsPage />} />
          </Routes>
        </div>
      </BrowserRouter>
    </CopilotKit>
  );
}
```

- [ ] **Step 10: Create stub pages so the build resolves imports**

`agui-frontend/src/pages/DashboardPage.tsx`:
```tsx
export default function DashboardPage() {
  return <div style={{ color: "#e0e0e0", padding: 16, fontFamily: "monospace" }}>Dashboard (coming soon)</div>;
}
```

`agui-frontend/src/pages/AgentsPage.tsx`:
```tsx
export default function AgentsPage() {
  return <div style={{ color: "#e0e0e0", padding: 16, fontFamily: "monospace" }}>Agents (coming soon)</div>;
}
```

These stubs are replaced with real implementations in Task 9.

- [ ] **Step 11: Install dependencies and verify build compiles**

```bash
cd agui-frontend
npm install
npm run build
```
Expected: build succeeds with no TypeScript errors.

- [ ] **Step 12: Commit**

```bash
cd ..
git add agui-frontend/
git commit -m "feat: scaffold React + CopilotKit frontend"
```

---

## Task 5: Data hooks

**Files:**
- Create: `agui-frontend/src/hooks/useStats.ts`
- Create: `agui-frontend/src/hooks/useAgents.ts`
- Create: `agui-frontend/src/hooks/useStats.test.ts`
- Create: `agui-frontend/src/hooks/useAgents.test.ts`

- [ ] **Step 1: Write failing test for useStats**

`agui-frontend/src/hooks/useStats.test.ts`:
```typescript
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
```

- [ ] **Step 2: Run test to confirm failure**

```bash
cd agui-frontend
npm test -- src/hooks/useStats.test.ts
```
Expected: FAIL — `useStats` not found.

- [ ] **Step 3: Create `agui-frontend/src/hooks/useStats.ts`**

```typescript
import { useState, useEffect } from "react";
import type { StatsResponse } from "../types";

interface UseStatsResult {
  data: StatsResponse | null;
  error: string | null;
  loading: boolean;
}

export function useStats(intervalMs = 60_000): UseStatsResult {
  const [data, setData] = useState<StatsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function fetchStats() {
      try {
        const resp = await fetch("/stats");
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const json: StatsResponse = await resp.json();
        if (!cancelled) {
          setData(json);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchStats();
    const id = setInterval(fetchStats, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [intervalMs]);

  return { data, error, loading };
}
```

- [ ] **Step 4: Run test to confirm pass**

```bash
npm test -- src/hooks/useStats.test.ts
```
Expected: PASS.

- [ ] **Step 5: Write failing test for useAgents**

`agui-frontend/src/hooks/useAgents.test.ts`:
```typescript
import { renderHook, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import { useAgents } from "./useAgents";

const MOCK_AGENTS = {
  agents: [
    { name: "sleep", url: "http://agent-sleep:8001", online: true, capabilities: ["analyze_sleep"], description: "", tasks_today: 3 },
    { name: "workout", url: "http://agent-workout:8002", online: false, capabilities: ["log_workout"], description: "", tasks_today: 0 },
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
```

- [ ] **Step 6: Run test to confirm failure**

```bash
npm test -- src/hooks/useAgents.test.ts
```
Expected: FAIL — `useAgents` not found.

- [ ] **Step 7: Create `agui-frontend/src/hooks/useAgents.ts`**

```typescript
import { useState, useEffect } from "react";
import type { AgentInfo, AgentsResponse } from "../types";

interface UseAgentsResult {
  agents: AgentInfo[];
  error: string | null;
  loading: boolean;
}

export function useAgents(intervalMs = 10_000): UseAgentsResult {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function fetchAgents() {
      try {
        const resp = await fetch("/agents");
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const json: AgentsResponse = await resp.json();
        if (!cancelled) {
          setAgents(json.agents);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchAgents();
    const id = setInterval(fetchAgents, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [intervalMs]);

  return { agents, error, loading };
}
```

- [ ] **Step 8: Run all hook tests**

```bash
npm test -- src/hooks/
```
Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
cd ..
git add agui-frontend/src/hooks/ agui-frontend/src/types.ts
git commit -m "feat: add useStats and useAgents data hooks"
```

---

## Task 6: DashboardPanel component

**Files:**
- Create: `agui-frontend/src/components/DashboardPanel.tsx`

- [ ] **Step 1: Write render test**

Create `agui-frontend/src/components/DashboardPanel.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { DashboardPanel } from "./DashboardPanel";
import type { StatsResponse } from "../types";

const STATS: StatsResponse = {
  agents: {
    sleep: { tasks_week: 5, tasks_prev_week: 3, delta: 2 },
    workout: { tasks_week: 3, tasks_prev_week: 4, delta: -1 },
    nutrition: { tasks_week: 4, tasks_prev_week: 2, delta: 2 },
  },
  activity: [
    { agent: "sleep", task_type: "analyze_sleep", message: "slept 7h", created_at: "2026-04-13T08:00:00Z" },
  ],
};

describe("DashboardPanel", () => {
  it("renders stat cards for each agent", () => {
    render(<DashboardPanel stats={STATS} />);
    expect(screen.getByText(/sleep/i)).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText(/slept 7h/i)).toBeInTheDocument();
  });

  it("renders loading state when stats is null", () => {
    render(<DashboardPanel stats={null} />);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to confirm failure**

```bash
cd agui-frontend && npm test -- src/components/DashboardPanel.test.tsx
```
Expected: FAIL — component not found.

- [ ] **Step 3: Create `agui-frontend/src/components/DashboardPanel.tsx`**

```tsx
import type { StatsResponse, ActivityItem, AgentStats } from "../types";

const AGENT_CONFIG = {
  sleep:     { emoji: "😴", label: "Sleep",     color: "#4a9eff" },
  workout:   { emoji: "💪", label: "Workout",   color: "#4eff9a" },
  nutrition: { emoji: "🥗", label: "Nutrition", color: "#ffb74a" },
} as const;

type AgentKey = keyof typeof AGENT_CONFIG;

function StatCard({ agentKey, stats }: { agentKey: AgentKey; stats: AgentStats }) {
  const cfg = AGENT_CONFIG[agentKey];
  const deltaStr = stats.delta > 0 ? `↑ ${stats.delta}` : stats.delta < 0 ? `↓ ${Math.abs(stats.delta)}` : "→ same";
  const deltaColor = stats.delta > 0 ? "#4eff9a" : stats.delta < 0 ? "#e57373" : "#888";
  return (
    <div style={{ background: "#1a1a2e", borderRadius: 6, padding: "10px 12px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <div>
        <div style={{ color: "#555", fontSize: 9, marginBottom: 2 }}>{cfg.emoji} {cfg.label} this week</div>
        <div style={{ fontSize: 20, fontWeight: "bold", color: cfg.color }}>{stats.tasks_week}</div>
      </div>
      <div style={{ fontSize: 9, color: deltaColor }}>{deltaStr}</div>
    </div>
  );
}

function BarChart({ agentKey, stats }: { agentKey: AgentKey; stats: AgentStats }) {
  const cfg = AGENT_CONFIG[agentKey];
  // Show 7 bars with rough daily breakdown (tasks_week distributed evenly as illustration)
  const maxVal = Math.max(1, stats.tasks_week);
  const bars = Array.from({ length: 7 }, (_, i) => {
    // Use a simple hash to distribute bars visually
    const val = i === 6 ? Math.ceil(stats.tasks_week / 7) : Math.floor(stats.tasks_week / 7);
    return Math.min(1, val / maxVal);
  });
  const days = ["M", "T", "W", "T", "F", "S", "S"];
  return (
    <div>
      <div style={{ color: cfg.color, fontSize: 9, marginBottom: 4 }}>{cfg.emoji} {cfg.label} (tasks/day est.)</div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 32 }}>
        {bars.map((h, i) => (
          <div
            key={i}
            style={{ background: cfg.color, flex: 1, height: `${Math.max(8, h * 100)}%`, borderRadius: "2px 2px 0 0", opacity: 0.8 }}
          />
        ))}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", color: "#444", fontSize: 8, marginTop: 2 }}>
        {days.map((d, i) => <span key={i}>{d}</span>)}
      </div>
    </div>
  );
}

function ActivityFeed({ items }: { items: ActivityItem[] }) {
  return (
    <div>
      <div style={{ color: "#555", fontSize: 9, textTransform: "uppercase", letterSpacing: 1, marginBottom: 6 }}>Recent activity</div>
      {items.length === 0 && <div style={{ color: "#444", fontSize: 10 }}>No activity yet</div>}
      {items.map((item, i) => {
        const cfg = AGENT_CONFIG[item.agent as AgentKey] ?? AGENT_CONFIG.sleep;
        const ts = new Date(item.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        const date = new Date(item.created_at).toLocaleDateString([], { month: "short", day: "numeric" });
        return (
          <div key={i}>
            <div style={{ display: "flex", gap: 8, alignItems: "flex-start", padding: "6px 0" }}>
              <span style={{ fontSize: 13 }}>{cfg.emoji}</span>
              <div>
                <div style={{ fontSize: 10, color: "#ddd" }}>{item.message || item.task_type}</div>
                <div style={{ fontSize: 9, color: "#444" }}>{date} {ts}</div>
              </div>
            </div>
            {i < items.length - 1 && <div style={{ height: 1, background: "#1e1e30", marginLeft: 22 }} />}
          </div>
        );
      })}
    </div>
  );
}

interface Props {
  stats: StatsResponse | null;
}

export function DashboardPanel({ stats }: Props) {
  if (!stats) {
    return (
      <div style={{ padding: 16, color: "#555", fontSize: 11, fontFamily: "monospace" }}>Loading...</div>
    );
  }

  const agents: AgentKey[] = ["sleep", "workout", "nutrition"];

  return (
    <div style={{
      width: 260,
      minWidth: 260,
      background: "#13131f",
      borderRight: "1px solid #1e1e30",
      overflowY: "auto",
      padding: 16,
      display: "flex",
      flexDirection: "column",
      gap: 14,
      fontFamily: "monospace",
    }}>
      {/* Stat cards */}
      <div>
        <div style={{ color: "#555", fontSize: 9, textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>Last 7 days</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {agents.map(a => <StatCard key={a} agentKey={a} stats={stats.agents[a]} />)}
        </div>
      </div>

      {/* Bar charts */}
      <div>
        <div style={{ color: "#555", fontSize: 9, textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>Trends</div>
        <div style={{ background: "#1a1a2e", borderRadius: 6, padding: 10, display: "flex", flexDirection: "column", gap: 10 }}>
          {agents.map(a => <BarChart key={a} agentKey={a} stats={stats.agents[a]} />)}
        </div>
      </div>

      {/* Activity feed */}
      <ActivityFeed items={stats.activity} />
    </div>
  );
}
```

- [ ] **Step 4: Run test**

```bash
npm test -- src/components/DashboardPanel.test.tsx
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ..
git add agui-frontend/src/components/DashboardPanel.tsx agui-frontend/src/components/DashboardPanel.test.tsx
git commit -m "feat: add DashboardPanel with stats cards, charts, and activity feed"
```

---

## Task 7: ChatPanel component

**Files:**
- Create: `agui-frontend/src/components/ChatPanel.tsx`

- [ ] **Step 1: Write render test**

`agui-frontend/src/components/ChatPanel.test.tsx`:
```tsx
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
```

- [ ] **Step 2: Run test to confirm failure**

```bash
cd agui-frontend && npm test -- src/components/ChatPanel.test.tsx
```
Expected: FAIL — component not found.

- [ ] **Step 3: Create `agui-frontend/src/components/ChatPanel.tsx`**

```tsx
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
```

- [ ] **Step 4: Run test**

```bash
npm test -- src/components/ChatPanel.test.tsx
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ..
git add agui-frontend/src/components/ChatPanel.tsx agui-frontend/src/components/ChatPanel.test.tsx
git commit -m "feat: add ChatPanel with CopilotKit chat"
```

---

## Task 8: Agents tab components

**Files:**
- Create: `agui-frontend/src/components/AgentCard.tsx`
- Create: `agui-frontend/src/components/AgentGraph.tsx`

- [ ] **Step 1: Write render tests**

`agui-frontend/src/components/AgentGraph.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { AgentGraph } from "./AgentGraph";
import type { AgentInfo } from "../types";

const AGENTS: AgentInfo[] = [
  { name: "sleep", url: "http://agent-sleep:8001", online: true, capabilities: ["analyze_sleep"], description: "", tasks_today: 2 },
  { name: "workout", url: "http://agent-workout:8002", online: false, capabilities: ["log_workout"], description: "", tasks_today: 0 },
  { name: "nutrition", url: "http://agent-nutrition:8003", online: true, capabilities: ["log_meal"], description: "", tasks_today: 1 },
];

describe("AgentGraph", () => {
  it("renders orchestrator node", () => {
    render(<AgentGraph agents={AGENTS} selectedAgent={null} onSelect={() => {}} />);
    expect(screen.getByText(/orchestrator/i)).toBeInTheDocument();
  });

  it("renders all agent names", () => {
    render(<AgentGraph agents={AGENTS} selectedAgent={null} onSelect={() => {}} />);
    expect(screen.getByText("sleep")).toBeInTheDocument();
    expect(screen.getByText("workout")).toBeInTheDocument();
    expect(screen.getByText("nutrition")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to confirm failure**

```bash
cd agui-frontend && npm test -- src/components/AgentGraph.test.tsx
```
Expected: FAIL.

- [ ] **Step 3: Create `agui-frontend/src/components/AgentCard.tsx`**

```tsx
import type { AgentInfo } from "../types";

const AGENT_CONFIG: Record<string, { emoji: string; color: string }> = {
  sleep:     { emoji: "😴", color: "#4a9eff" },
  workout:   { emoji: "💪", color: "#4eff9a" },
  nutrition: { emoji: "🥗", color: "#ffb74a" },
};

interface Props {
  agent: AgentInfo;
  onClose: () => void;
}

export function AgentCard({ agent, onClose }: Props) {
  const cfg = AGENT_CONFIG[agent.name] ?? { emoji: "🤖", color: "#aaa" };
  return (
    <div style={{
      background: "#13131f",
      border: "1px solid #1e1e30",
      borderRadius: 8,
      padding: "16px 20px",
      width: 300,
      fontFamily: "monospace",
      color: "#e0e0e0",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 20 }}>{cfg.emoji}</span>
          <span style={{ fontSize: 13, fontWeight: "bold" }}>{agent.name}-agent</span>
        </div>
        <button
          onClick={onClose}
          style={{ background: "none", border: "none", color: "#555", cursor: "pointer", fontSize: 16 }}
        >
          ×
        </button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 11 }}>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span style={{ color: "#555" }}>Status</span>
          <span style={{ color: agent.online ? "#4eff9a" : "#e57373" }}>
            {agent.online ? "● online" : "● offline"}
          </span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span style={{ color: "#555" }}>Port</span>
          <span>{agent.url.split(":").pop()}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span style={{ color: "#555" }}>Tasks today</span>
          <span style={{ color: cfg.color }}>{agent.tasks_today}</span>
        </div>
        {agent.description && (
          <div style={{ color: "#888", fontSize: 10, marginTop: 4 }}>{agent.description}</div>
        )}
        <div style={{ marginTop: 8 }}>
          <div style={{ color: "#555", fontSize: 9, textTransform: "uppercase", letterSpacing: 1, marginBottom: 6 }}>Capabilities</div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {agent.capabilities.map(cap => (
              <span key={cap} style={{
                background: "#0f3460",
                borderRadius: 10,
                padding: "3px 8px",
                fontSize: 9,
                color: cfg.color,
              }}>
                {cap}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create `agui-frontend/src/components/AgentGraph.tsx`**

```tsx
import type { AgentInfo } from "../types";

const AGENT_CONFIG: Record<string, { emoji: string; color: string }> = {
  sleep:     { emoji: "😴", color: "#4a9eff" },
  workout:   { emoji: "💪", color: "#4eff9a" },
  nutrition: { emoji: "🥗", color: "#ffb74a" },
};

interface Props {
  agents: AgentInfo[];
  selectedAgent: string | null;
  onSelect: (name: string | null) => void;
}

export function AgentGraph({ agents, selectedAgent, onSelect }: Props) {
  const onlineCount = agents.filter(a => a.online).length;

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      gap: 24,
      padding: "32px 16px",
      fontFamily: "monospace",
    }}>
      {/* Orchestrator node */}
      <div style={{
        background: "#0f3460",
        border: "1px solid #4a9eff",
        borderRadius: 8,
        padding: "12px 28px",
        textAlign: "center",
        color: "#4a9eff",
      }}>
        <div style={{ fontSize: 9, opacity: 0.7, marginBottom: 2 }}>orchestrator</div>
        <div style={{ fontSize: 11, fontWeight: "bold" }}>:8000</div>
        <div style={{ fontSize: 9, color: "#555", marginTop: 4 }}>{onlineCount}/{agents.length} agents online</div>
      </div>

      {/* Connection lines SVG */}
      <svg width={agents.length * 120} height={32} style={{ overflow: "visible" }}>
        {agents.map((_, i) => {
          const totalW = agents.length * 120;
          const x = (i + 0.5) * (totalW / agents.length);
          return (
            <line
              key={i}
              x1={totalW / 2} y1={0}
              x2={x} y2={32}
              stroke="#2a2a4a"
              strokeWidth={1}
              strokeDasharray="4,4"
            />
          );
        })}
      </svg>

      {/* Agent nodes */}
      <div style={{ display: "flex", gap: 16 }}>
        {agents.map(agent => {
          const cfg = AGENT_CONFIG[agent.name] ?? { emoji: "🤖", color: "#aaa" };
          const isSelected = selectedAgent === agent.name;
          return (
            <div
              key={agent.name}
              onClick={() => onSelect(isSelected ? null : agent.name)}
              style={{
                background: "#16213e",
                border: `1px solid ${isSelected ? cfg.color : (agent.online ? "#1e3a1e" : "#3a1e1e")}`,
                borderRadius: 8,
                padding: "14px 18px",
                textAlign: "center",
                width: 100,
                cursor: "pointer",
                transition: "border-color 0.15s",
              }}
            >
              <div style={{ fontSize: 22 }}>{cfg.emoji}</div>
              <div style={{ color: "#aaa", marginTop: 4, fontSize: 10 }}>{agent.name}</div>
              <div style={{ color: "#555", fontSize: 9 }}>:{agent.url.split(":").pop()}</div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 4, marginTop: 6 }}>
                <div style={{ width: 6, height: 6, borderRadius: "50%", background: agent.online ? "#4eff9a" : "#e57373" }} />
                <div style={{ fontSize: 8, color: agent.online ? "#4eff9a" : "#e57373" }}>
                  {agent.online ? "online" : "offline"}
                </div>
              </div>
              <div style={{ fontSize: 9, color: "#555", marginTop: 4 }}>{agent.tasks_today} tasks today</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Run test**

```bash
npm test -- src/components/AgentGraph.test.tsx
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd ..
git add agui-frontend/src/components/AgentCard.tsx agui-frontend/src/components/AgentGraph.tsx agui-frontend/src/components/AgentGraph.test.tsx
git commit -m "feat: add AgentGraph and AgentCard components"
```

---

## Task 9: Pages

**Files:**
- Create: `agui-frontend/src/pages/DashboardPage.tsx`
- Create: `agui-frontend/src/pages/AgentsPage.tsx`

- [ ] **Step 1: Create `agui-frontend/src/pages/DashboardPage.tsx`**

```tsx
import { DashboardPanel } from "../components/DashboardPanel";
import { ChatPanel } from "../components/ChatPanel";
import { useStats } from "../hooks/useStats";

export default function DashboardPage() {
  const { data } = useStats();
  return (
    <div style={{ display: "flex", height: "calc(100vh - 41px)", overflow: "hidden" }}>
      <DashboardPanel stats={data} />
      <ChatPanel />
    </div>
  );
}
```

- [ ] **Step 2: Create `agui-frontend/src/pages/AgentsPage.tsx`**

```tsx
import { useState } from "react";
import { AgentGraph } from "../components/AgentGraph";
import { AgentCard } from "../components/AgentCard";
import { useAgents } from "../hooks/useAgents";
import type { AgentInfo } from "../types";

export default function AgentsPage() {
  const { agents, loading, error } = useAgents();
  const [selected, setSelected] = useState<string | null>(null);

  const selectedAgent: AgentInfo | undefined = agents.find(a => a.name === selected);

  if (loading) {
    return <div style={{ padding: 32, color: "#555", fontFamily: "monospace" }}>Discovering agents...</div>;
  }

  if (error) {
    return <div style={{ padding: 32, color: "#e57373", fontFamily: "monospace" }}>Error: {error}</div>;
  }

  return (
    <div style={{ padding: 32, display: "flex", flexDirection: "column", alignItems: "center", gap: 24 }}>
      <h2 style={{ color: "#e0e0e0", fontFamily: "monospace", fontWeight: "normal", margin: 0 }}>
        Agent Topology
      </h2>
      <AgentGraph agents={agents} selectedAgent={selected} onSelect={setSelected} />
      {selectedAgent && (
        <AgentCard agent={selectedAgent} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
```

- [ ] **Step 3: Verify build**

```bash
cd agui-frontend && npm run build
```
Expected: build succeeds with no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
cd ..
git add agui-frontend/src/pages/
git commit -m "feat: add DashboardPage and AgentsPage"
```

---

## Task 10: Docker + nginx + docker-compose

**Files:**
- Create: `agui-frontend/Dockerfile`
- Create: `agui-frontend/nginx.conf`
- Create: `agui-frontend/.dockerignore`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Create `agui-frontend/.dockerignore`**

```
node_modules
dist
.git
*.test.ts
*.test.tsx
```

- [ ] **Step 2: Create `agui-frontend/nginx.conf`**

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

    location /agents {
        proxy_pass http://orchestrator:8000;
    }

    location /health {
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

- [ ] **Step 3: Create `agui-frontend/Dockerfile`**

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

- [ ] **Step 4: Add `agui-frontend` to `docker-compose.yml`**

Add this service block before the `volumes:` section at the bottom of `docker-compose.yml`:
```yaml
  agui-frontend:
    build:
      context: ./agui-frontend
    ports:
      - "3000:80"
    depends_on:
      orchestrator:
        condition: service_started
    restart: unless-stopped
```

- [ ] **Step 5: Test Docker build locally**

```bash
cd agui-frontend && docker build -t agui-frontend-test .
```
Expected: image builds successfully. Both stages complete.

- [ ] **Step 6: Commit**

```bash
cd ..
git add agui-frontend/Dockerfile agui-frontend/nginx.conf agui-frontend/.dockerignore docker-compose.yml
git commit -m "feat: add agui-frontend Docker container and nginx proxy config"
```

---

## Task 11: End-to-end smoke test

- [ ] **Step 1: Run all Python tests**

```bash
pytest tests/ -v
```
Expected: all PASS.

- [ ] **Step 2: Run all frontend tests**

```bash
cd agui-frontend && npm test
```
Expected: all PASS.

- [ ] **Step 3: Start the full stack**

```bash
cd ..
source scripts/export-auth.sh  # exports Claude OAuth token to .env.auth
docker compose up --build
```
Expected: all containers start. `agui-frontend` builds and runs on port 3000.

- [ ] **Step 4: Verify frontend loads**

Open `http://localhost:3000` in browser.
Expected:
- Dashboard tab shows (may show "Loading..." until agents respond)
- Agents tab shows orchestrator node + 3 agent nodes with online/offline status
- Chat input accepts a message and streams a response

- [ ] **Step 5: Verify SSE stream manually**

```bash
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"How was my sleep?"}]}'
```
Expected output:
```
data: {"type":"RunStarted",...}
data: {"type":"TextMessageStart",...}
data: {"type":"TextMessageContent","delta":"..."}
...
data: {"type":"RunFinished",...}
```

- [ ] **Step 6: Final commit**

```bash
git add .
git commit -m "feat: Plan 4 complete — AG-UI React frontend with SSE streaming"
```

---

## Appendix: CopilotKit theming note

`index.css` is created in Task 4 and imported in `main.tsx` with CSS variables for the dark theme. If CopilotKit's chat component doesn't pick up these variables cleanly (theming API is version-dependent), inspect the rendered component classes in browser DevTools and add targeted overrides to `index.css`.
