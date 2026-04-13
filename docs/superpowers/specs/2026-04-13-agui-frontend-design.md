# AG-UI Frontend — Design Spec
_Date: 2026-04-13_

## Overview

A React + CopilotKit web frontend for the life-agents system. Runs as a Docker container (`agui-frontend`, port 3000), served by nginx. Two tabs: **Dashboard + Chat** (default) and **Agents**. Talks only to the orchestrator — never directly to agents.

---

## 1. Architecture

### New container

| Container | Role | Port |
|---|---|---|
| `agui-frontend` | Vite + React app, served by nginx | 3000 |

nginx proxies API calls to `http://orchestrator:8000` by Docker service name, so the browser never hits a different origin.

### Orchestrator additions (no new container)

| Endpoint | Change |
|---|---|
| `POST /chat/stream` | New — SSE streaming endpoint, AG-UI protocol |
| `GET /stats` | New — 7-day health aggregates + activity feed from Postgres |
| `GET /agents` | Extended — add `capabilities`, `tasks_today`, live health recheck per call |
| `POST /chat` | Existing — untouched (Telegram uses this) |
| CORS | Add `CORSMiddleware` allowing `http://localhost:3000` |

### Data flow

```
Browser → POST /chat/stream (SSE)
    → orchestrator classifies intent → POSTs to agent
    → agent returns full text response
    → orchestrator emits AG-UI events (chunked)
    → CopilotKit renders streaming chat bubble

Browser → GET /stats (on load + every 60s)
    → orchestrator queries Postgres
    → returns metrics + recent activity feed

Browser → GET /agents (every 10s)
    → orchestrator returns agent registry (name, url, status, capabilities, tasks_today)
    → orchestrator re-checks each agent's health on each /agents call
```

---

## 2. Frontend Structure

```
agui-frontend/
  src/
    App.tsx                  # Router, CopilotKit provider
    pages/
      DashboardPage.tsx      # Layout: DashboardPanel + ChatPanel side by side
      AgentsPage.tsx         # Agent topology view
    components/
      DashboardPanel.tsx     # Stats cards + bar charts + activity feed
      ChatPanel.tsx          # CopilotKit chat wrapper
      AgentGraph.tsx         # Node graph: orchestrator → agents
      AgentCard.tsx          # Per-agent: status, task count, capabilities
    hooks/
      useStats.ts            # GET /stats, polling every 60s
      useAgents.ts           # GET /agents, polling every 10s
    types.ts                 # Shared TS interfaces
  nginx.conf
  Dockerfile
  package.json
```

### Routing

- `/` — DashboardPage (default)
- `/agents` — AgentsPage

### CopilotKit wiring

```tsx
// App.tsx
<CopilotKit runtimeUrl="/chat/stream">
  <Router>
    <nav> {/* Dashboard | Agents tabs */} </nav>
    <Routes>
      <Route path="/" element={<DashboardPage />} />
      <Route path="/agents" element={<AgentsPage />} />
    </Routes>
  </Router>
</CopilotKit>
```

`ChatPanel` renders `<CopilotChat />` — handles streaming bubbles, typing indicator, and scroll out of the box.

### Dashboard panel sections (top to bottom)

1. **Key metrics** — stat cards for sleep avg (h), workout count, calorie avg with week-over-week delta indicators
2. **Trends** — mini bar charts (7 bars, one per day) for sleep hours and workout presence
3. **Recent activity** — chronological feed of last 10 `health_logs` entries across all agents

### Agents tab

- Node graph: orchestrator in centre, three agent nodes below connected by dashed lines
- Each agent node shows: emoji icon, name, port, online/offline dot
- Clicking an agent shows `AgentCard` with: status, tasks completed today, capabilities list (all sourced from `/agents` — no browser-to-agent calls)
- Orchestrator node shows: last routed agent + timestamp

---

## 3. Orchestrator: `/chat/stream`

Accepts the same `ChatRequest` body as `/chat`. Returns `Content-Type: text/event-stream`.

### AG-UI event sequence

```
data: {"type":"RunStarted","threadId":"<uuid>","runId":"<uuid>"}

data: {"type":"TextMessageStart","messageId":"<uuid>","role":"assistant"}

data: {"type":"TextMessageContent","messageId":"<uuid>","delta":"<chunk>"}
... (repeated, ~5 words per chunk)

data: {"type":"TextMessageEnd","messageId":"<uuid>"}

data: {"type":"RunFinished","threadId":"<uuid>","runId":"<uuid>"}
```

The agent response arrives as a single string (Claude CLI via subprocess). The orchestrator splits it into ~5-word chunks and emits them sequentially. No changes required to any agent.

FastAPI implementation uses `StreamingResponse` with an async generator:

```python
async def event_stream(message: str):
    yield format_event({"type": "RunStarted", ...})
    # call agent, get full response
    for chunk in split_into_chunks(response, size=5):
        yield format_event({"type": "TextMessageContent", "delta": chunk})
        await asyncio.sleep(0.02)
    yield format_event({"type": "RunFinished", ...})

return StreamingResponse(event_stream(req.message), media_type="text/event-stream")
```

---

## 4. Orchestrator: `/stats`

Queries Postgres via `shared/db.py`. Returns JSON:

```json
{
  "sleep": { "avg_hours": 6.8, "delta": -0.7 },
  "workouts": { "count": 3, "delta": 1 },
  "nutrition": { "avg_calories": 2100, "delta": 0 },
  "activity": [
    { "agent": "sleep", "type": "sleep_session", "data": {...}, "recorded_at": "..." },
    ...
  ]
}
```

- Averages computed over the last 7 days vs the prior 7 days (for delta)
- `activity` — last 10 `health_logs` rows ordered by `recorded_at DESC`

---

## 5. Docker & Build

### `agui-frontend/Dockerfile`

Two-stage build:

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
```

### `nginx.conf`

```nginx
server {
  listen 80;

  location /chat/ {
    proxy_pass http://orchestrator:8000;
    proxy_buffering off;
    proxy_cache off;
    proxy_set_header Connection '';
    proxy_http_version 1.1;
  }

  location /stats {
    proxy_pass http://orchestrator:8000;
  }

  location /agents {
    proxy_pass http://orchestrator:8000;
  }

  location / {
    root /usr/share/nginx/html;
    try_files $uri /index.html;
  }
}
```

`proxy_buffering off` is required on the `/chat/` route so SSE events are not held in nginx's buffer.

### `docker-compose.yml` addition

```yaml
agui-frontend:
  build:
    context: ./agui-frontend
  ports:
    - "3000:80"
  depends_on:
    - orchestrator
```

---

## 6. Visual Design

- Dark theme throughout (matches mockup): background `#0d0d1a`, panels `#13131f`, cards `#1a1a2e`
- Agent colours: sleep `#4a9eff` (blue), workout `#4eff9a` (green), nutrition `#ffb74a` (amber)
- Online indicator: `#4eff9a` dot; offline: `#e57373` dot
- Font: system monospace stack

---

## 7. Out of Scope

- Authentication (local use only)
- Light mode toggle
- Mobile layout
- True per-token streaming from Claude CLI (requires agent changes — deferred)
- Historical chart views beyond 7 days
