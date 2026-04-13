# A2A Inter-Agent Communication Design

**Date:** 2026-04-13  
**Status:** Approved

## Overview

Implement Google Agent-to-Agent (A2A) protocol across all agents so that the primary agent (determined by the orchestrator) can call peer agents as A2A sub-tasks, collect their Artifacts, and return a single grouped response. Replace passive shared-DB context with live A2A calls between agents.

---

## 1. A2A Task/Artifact Structures

### Task Object

All `POST /tasks` endpoints return a standard A2A Task object:

```json
{
  "id": "uuid",
  "status": {
    "state": "completed",
    "timestamp": "2026-04-13T12:00:00Z"
  },
  "artifacts": [
    {
      "name": "analysis",
      "parts": [{ "type": "text", "text": "..." }]
    }
  ]
}
```

Task lifecycle states: `submitted → working → completed | failed`

### Task Request

```json
{
  "id": "uuid",
  "task": "analyze_workout",
  "params": {
    "message": "user message",
    "peer_agents": {
      "sleep":     { "url": "http://agent-sleep:8001",     "card": { ... } },
      "nutrition": { "url": "http://agent-nutrition:8003", "card": { ... } }
    },
    "webhook_url": "https://optional-webhook.example.com/notify"
  }
}
```

`peer_agents` is injected by the orchestrator. `webhook_url` is optional.

### Agent Card (enhanced)

```json
{
  "name": "workout-agent",
  "description": "...",
  "url": "http://agent-workout:8002",
  "version": "1.0.0",
  "capabilities": {
    "streaming": true,
    "pushNotifications": true
  },
  "skills": [
    {
      "id": "log_workout",
      "name": "Log Workout",
      "description": "Log a new workout session",
      "inputModes": ["text"],
      "outputModes": ["text"]
    },
    {
      "id": "analyze_workout",
      "name": "Analyze Workout",
      "description": "Analyze training load, trends, and recovery",
      "inputModes": ["text"],
      "outputModes": ["text"]
    },
    {
      "id": "get_recommendations",
      "name": "Get Recommendations",
      "description": "Recommend next session based on history and context",
      "inputModes": ["text"],
      "outputModes": ["text"]
    }
  ]
}
```

Same structure for sleep and nutrition agents with their respective skills.

---

## 2. Inter-Agent Call Flow

### Request Flow

```
User message
     │
     ▼
Orchestrator: classify_intent → primary agent (e.g. "workout")
     │
     ▼  POST /tasks  (A2A Task Request with peer_agents)
Workout Agent
     │
     ├─► POST http://agent-sleep:8001/tasks        (parallel, A2A sub-task)
     │       task: "analyze_sleep"
     │       ← Task { artifacts: [sleep analysis Artifact] }
     │
     ├─► POST http://agent-nutrition:8003/tasks    (parallel, A2A sub-task)
     │       task: "analyze_nutrition"
     │       ← Task { artifacts: [nutrition analysis Artifact] }
     │
     ▼
Workout synthesizes all Artifacts → single grouped Artifact:

  ## Тренировка
  [workout analysis]

  ## Сон  (sleep-agent)
  [sleep analysis]

  ## Питание  (nutrition-agent)
  [nutrition analysis]

  ## Рекомендации
  [cross-domain synthesis]
```

### Peer Call Rules

- Sub-task calls to peers are **parallel** (`asyncio.gather`)
- If a peer is unavailable, its section is marked `(данные недоступны)` — the primary task does not fail
- Sub-tasks pass `"context": "requested by <primary-agent>"` in params so peers know to give a summary, not a full interactive response
- Sub-tasks do **not** receive `peer_agents` themselves — no recursive chaining

### Orchestrator Changes

The orchestrator builds `peer_agents` from its registry (already populated at startup via `discover_agents`). It passes all agents except the primary as peers.

---

## 3. Streaming (SSE) and Push Notifications

### Streaming Endpoint

Each agent adds `POST /tasks/stream` — an SSE endpoint emitting Task status events:

```
data: {"id": "...", "status": {"state": "submitted"}}
data: {"id": "...", "status": {"state": "working"}}
data: {"id": "...", "status": {"state": "working"}, "artifacts": [{"name": "peer_sleep", ...}]}
data: {"id": "...", "status": {"state": "working"}, "artifacts": [{"name": "peer_nutrition", ...}]}
data: {"id": "...", "status": {"state": "completed"}, "artifacts": [{"name": "analysis", ...}]}
```

Events are emitted at each stage:
1. Task accepted → `submitted`
2. Sub-task calls started → `working`
3. Each peer result arrives → `working` + partial artifact
4. Synthesis complete → `completed` + final artifact

### Orchestrator Streaming

`POST /chat/stream` calls primary agent at `/tasks/stream` and proxies SSE events to the frontend. Frontend already handles SSE — the `TextMessageContent` delta is fed from artifact `parts[0].text`.

### Push Notifications

- Task Request may include optional `webhook_url`
- On `completed` or `failed`, agent does `POST webhook_url` with the final Task object
- Fire-and-forget (`asyncio.create_task`), failures are logged but not surfaced to caller
- Not used internally within the system — intended for external integrations

---

## 4. Shared Module: `shared/a2a.py`

New shared module to avoid duplicating A2A types across all agents:

```python
# shared/shared/a2a.py

from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime, timezone
import uuid

class TaskStatus(BaseModel):
    state: Literal["submitted", "working", "completed", "failed"]
    timestamp: str = ""

    @classmethod
    def now(cls, state):
        return cls(state=state, timestamp=datetime.now(timezone.utc).isoformat())

class TextPart(BaseModel):
    type: Literal["text"] = "text"
    text: str

class Artifact(BaseModel):
    name: str
    parts: list[TextPart]

class Task(BaseModel):
    id: str
    status: TaskStatus
    artifacts: list[Artifact] = []

class TaskRequest(BaseModel):
    id: str = ""
    task: str
    params: dict = {}
```

---

## 5. Files Changed

| File | Change |
|------|--------|
| `shared/shared/a2a.py` | New — A2A Pydantic models |
| `agents/workout/app/agent_card.py` | Add `capabilities`, `skills` fields |
| `agents/sleep/app/agent_card.py` | Same |
| `agents/nutrition/app/agent_card.py` | Same |
| `agents/workout/app/main.py` | Update `/tasks` to accept/return A2A Task; add `/tasks/stream` |
| `agents/sleep/app/main.py` | Same |
| `agents/nutrition/app/main.py` | Same |
| `agents/workout/app/tasks.py` | Call peer agents via A2A, synthesize grouped artifact |
| `agents/sleep/app/tasks.py` | Return A2A Task; handle `context` param for peer summary mode |
| `agents/nutrition/app/tasks.py` | Same |
| `agents/workout/app/prompt.py` | Add peer artifacts to prompt context; remove passive DB reads for nutrition |
| `orchestrator/app/main.py` | Build `peer_agents` from registry; pass in task request; proxy stream |

---

## 6. Out of Scope

- Multi-hop chaining (peer calling another peer)
- Authentication between agents (internal network trust)
- Task cancellation (`canceled` state)
- Persistent task storage / task polling by ID
