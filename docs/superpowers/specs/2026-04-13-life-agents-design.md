# Life Agents — Design Spec
_Date: 2026-04-13_

## Overview

A local Docker-based multi-agent system for personal health improvement. Agents run independently, communicate via Google A2A protocol, and are powered by the `claude` CLI (Claude subscription, no API key). The user interacts through a Telegram bot and an AG-UI React frontend — both routing through a central orchestrator.

---

## 1. Architecture

### Container Layout

| Container | Role | Port |
|---|---|---|
| `orchestrator` | Accepts user requests, discovers agents, routes A2A tasks | 8000 |
| `agent-sleep` | Sleep tracking and recommendations | 8001 |
| `agent-workout` | Workout tracking and recommendations | 8002 |
| `agent-nutrition` | Nutrition tracking and recommendations | 8003 |
| `sync-service` | Pulls data from external sources (Apple Health, Garmin, etc.) on schedule | — |
| `telegram-bot` | Telegram interface, forwards to orchestrator | — |
| `agui-frontend` | React + CopilotKit frontend, SSE streaming | 3000 |
| `postgres` | Structured data (logs, metrics, user profile) | 5432 |
| `qdrant` | Vector memory for agents | 6333 |

All containers are defined in a single `docker-compose.yml`.

### Claude CLI Authorization

The `~/.claude` directory is mounted from the host as read-only into each agent container, providing subscription-based auth without an API key:

```yaml
volumes:
  - ~/.claude:/root/.claude:ro
```

---

## 2. A2A Communication

Each agent exposes an **Agent Card** at `GET /.well-known/agent.json`:

```json
{
  "name": "sleep-agent",
  "description": "Tracks sleep patterns and gives recommendations",
  "url": "http://agent-sleep:8001",
  "capabilities": ["analyze_sleep", "log_sleep", "get_recommendations"],
  "version": "1.0.0"
}
```

On startup, the orchestrator performs **discovery** — queries all agents for their Agent Cards and builds a registry. Agents that are down are marked unavailable; the orchestrator does not crash.

### Task Flow

```
User message
    ↓
Orchestrator: classifies intent → selects agent
    ↓
POST http://agent-{name}:{port}/tasks
{ "task": "...", "params": { ... } }
    ↓
Agent: builds prompt with context → runs claude CLI → returns result
    ↓
Orchestrator: streams response back to interface (SSE or polling)
```

Agents may call each other by routing requests through the orchestrator. No direct agent-to-agent HTTP calls — the orchestrator is always the intermediary.

---

## 3. Agent Internals

Each agent is a **Python + FastAPI** service. Structure per agent:

```
agent-sleep/
  main.py          # FastAPI app, A2A endpoints
  agent_card.py    # Agent Card definition
  tools.py         # Postgres/Qdrant read/write helpers
  prompt.py        # Prompt construction with context injection
  Dockerfile
  requirements.txt
```

### Claude CLI Execution

```python
import subprocess

result = subprocess.run(
    ["claude", "--print", prompt],
    capture_output=True, text=True
)
response = result.stdout
```

The agent:
1. Receives A2A task
2. Fetches relevant context from Postgres (recent logs) and Qdrant (semantic memory)
3. Builds prompt with context
4. Runs `claude --print`
5. Saves result to Postgres and Qdrant
6. Returns A2A response

---

## 4. Data Storage

### Postgres Schema

```sql
users (
  id uuid primary key,
  name text,
  timezone text,
  preferences jsonb
);

health_logs (
  id uuid primary key,
  agent text,           -- 'sleep' | 'workout' | 'nutrition'
  type text,            -- e.g. 'sleep_session', 'workout', 'meal'
  data jsonb,
  recorded_at timestamptz,
  source text           -- 'manual' | 'apple_health' | 'garmin' | ...
);

tasks (
  id uuid primary key,
  agent text,
  task_type text,
  input jsonb,
  output text,
  created_at timestamptz
);
```

### Qdrant Collections

One collection per agent:
- `sleep_memories`
- `workout_memories`
- `nutrition_memories`

Each memory entry: text embedding + metadata (`date`, `type`, `source`). Agents run semantic search before building prompts to inject relevant past context.

### External Data Sync

A `sync-service` container runs on a schedule (cron) to pull data from external integrations (Apple Health export, Garmin API, Strava, etc.) and write normalized records into Postgres `health_logs`. Agents are unaware of integrations — they only read from the DB.

---

## 5. Interfaces

### Telegram Bot

- Library: `python-telegram-bot`
- Commands: `/sleep`, `/workout`, `/nutrition` + free-form text
- Flow: message → `POST /chat` to orchestrator → wait for response → reply
- The orchestrator classifies free-form text to the correct agent

### AG-UI Frontend

- Library: React + CopilotKit
- Flow: browser → `POST /chat` (SSE endpoint on orchestrator) → stream AG-UI events
- Orchestrator emits: `RunStarted`, `TextMessageStart`, `TextMessageContent`, `TextMessageEnd`, `RunFinished`
- Both interfaces share the same orchestrator `/chat` endpoint; the orchestrator detects whether to stream (SSE) or return a single response (Telegram polling)

---

## 6. Anti-ban Considerations

- `claude` CLI is an official Anthropic tool — using it with a subscription is the intended use case
- The orchestrator naturally serializes requests: one agent responds at a time, no parallel `claude` invocations
- No rate-limit bypassing, no headless browser automation, no credential sharing

---

## 7. Out of Scope (for now)

- Agent-to-agent direct calls (always proxied through orchestrator)
- Authentication/authorization on the web frontend (local use only)
- Mobile app
- Event-driven message queue (can be added later as async transport)
