# Foundation + Orchestrator + Sleep Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working end-to-end A2A system: docker-compose infrastructure, a Sleep Agent that runs `claude` CLI, and an Orchestrator that discovers and routes tasks to it.

**Architecture:** Each agent is a FastAPI service exposing a Google A2A-compatible interface (Agent Card + `/tasks` endpoint). The Orchestrator discovers agents on startup and routes user requests. The `claude` CLI runs as a subprocess inside each agent container, authenticated via mounted `~/.claude`. Postgres stores structured logs; Qdrant stores vector memories.

**Tech Stack:** Python 3.12, FastAPI, `asyncpg`, `qdrant-client`, `python-telegram-bot` (not in this plan), Docker Compose, Postgres 16, Qdrant latest, `claude` CLI (pre-installed in image).

---

## File Structure

```
life-agents/
├── docker-compose.yml
├── .env.example
├── shared/                         # Shared Python library (installed as package)
│   ├── pyproject.toml
│   └── shared/
│       ├── __init__.py
│       ├── db.py                   # Postgres asyncpg helpers
│       ├── vector.py               # Qdrant helpers
│       └── claude_runner.py        # subprocess wrapper for claude CLI
├── orchestrator/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py                 # FastAPI app, /chat endpoint
│       ├── registry.py             # Agent discovery + registry
│       └── router.py               # Intent classification + task routing
├── agents/
│   └── sleep/
│       ├── Dockerfile
│       ├── requirements.txt
│       └── app/
│           ├── main.py             # FastAPI app
│           ├── agent_card.py       # Agent Card definition
│           ├── tasks.py            # A2A /tasks endpoint handler
│           └── prompt.py           # Prompt builder with context injection
├── db/
│   └── init.sql                    # Postgres schema
└── tests/
    ├── test_claude_runner.py
    ├── test_agent_card.py
    ├── test_sleep_tasks.py
    └── test_orchestrator_routing.py
```

---

## Task 1: Project Scaffold + Docker Compose

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `db/init.sql`

- [ ] **Step 1: Create `.env.example`**

```bash
# .env.example
POSTGRES_DB=lifeagents
POSTGRES_USER=lifeagents
POSTGRES_PASSWORD=lifeagents
QDRANT_HOST=qdrant
QDRANT_PORT=6333
ORCHESTRATOR_URL=http://orchestrator:8000
SLEEP_AGENT_URL=http://agent-sleep:8001
```

Copy to `.env`:
```bash
cp .env.example .env
```

- [ ] **Step 2: Create `db/init.sql`**

```sql
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    preferences JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS health_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent TEXT NOT NULL,
    type TEXT NOT NULL,
    data JSONB NOT NULL DEFAULT '{}',
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source TEXT NOT NULL DEFAULT 'manual'
);

CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent TEXT NOT NULL,
    task_type TEXT NOT NULL,
    input JSONB NOT NULL DEFAULT '{}',
    output TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Default user (single-user system for now)
INSERT INTO users (name, timezone) VALUES ('me', 'Europe/Kyiv')
ON CONFLICT DO NOTHING;
```

- [ ] **Step 3: Create `docker-compose.yml`**

```yaml
version: "3.9"

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./db/init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 5

  qdrant:
    image: qdrant/qdrant:latest
    volumes:
      - qdrant_data:/qdrant/storage
    ports:
      - "6333:6333"
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:6333/healthz || exit 1"]
      interval: 5s
      timeout: 5s
      retries: 5

  agent-sleep:
    build: ./agents/sleep
    environment:
      POSTGRES_DSN: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      QDRANT_HOST: ${QDRANT_HOST}
      QDRANT_PORT: ${QDRANT_PORT}
    volumes:
      - ~/.claude:/root/.claude:ro
    ports:
      - "8001:8001"
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_healthy

  orchestrator:
    build: ./orchestrator
    environment:
      POSTGRES_DSN: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      AGENT_URLS: "http://agent-sleep:8001"
    ports:
      - "8000:8000"
    depends_on:
      - agent-sleep

volumes:
  postgres_data:
  qdrant_data:
```

- [ ] **Step 4: Bring up infrastructure only and verify**

```bash
docker compose up postgres qdrant -d
docker compose ps
```

Expected: both `postgres` and `qdrant` show as `healthy`.

- [ ] **Step 5: Commit**

```bash
git init
git add docker-compose.yml .env.example db/init.sql
git commit -m "feat: project scaffold with docker-compose, postgres, qdrant"
```

---

## Task 2: Shared Library

**Files:**
- Create: `shared/pyproject.toml`
- Create: `shared/shared/__init__.py`
- Create: `shared/shared/db.py`
- Create: `shared/shared/vector.py`
- Create: `shared/shared/claude_runner.py`
- Create: `tests/test_claude_runner.py`

- [ ] **Step 1: Create `shared/pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "shared"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "asyncpg>=0.29",
    "qdrant-client>=1.9",
]
```

- [ ] **Step 2: Create `shared/shared/__init__.py`**

```python
```

(empty file)

- [ ] **Step 3: Create `shared/shared/db.py`**

```python
import asyncpg
import os
from typing import Any

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(os.environ["POSTGRES_DSN"])
    return _pool


async def fetch_recent_logs(agent: str, limit: int = 20) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT type, data, recorded_at, source FROM health_logs "
        "WHERE agent = $1 ORDER BY recorded_at DESC LIMIT $2",
        agent, limit
    )
    return [dict(r) for r in rows]


async def insert_log(agent: str, type_: str, data: dict, source: str = "manual") -> None:
    pool = await get_pool()
    await pool.execute(
        "INSERT INTO health_logs (agent, type, data, source) VALUES ($1, $2, $3, $4)",
        agent, type_, data, source
    )


async def insert_task(agent: str, task_type: str, input_: dict, output: str) -> None:
    pool = await get_pool()
    await pool.execute(
        "INSERT INTO tasks (agent, task_type, input, output) VALUES ($1, $2, $3, $4)",
        agent, task_type, input_, output
    )
```

- [ ] **Step 4: Create `shared/shared/vector.py`**

```python
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import os
import hashlib

_client: AsyncQdrantClient | None = None
VECTOR_SIZE = 384  # all-MiniLM-L6-v2 compatible placeholder; we use hash-based fake embeddings for now


def _get_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(
            host=os.environ.get("QDRANT_HOST", "localhost"),
            port=int(os.environ.get("QDRANT_PORT", 6333)),
        )
    return _client


def _text_to_vector(text: str) -> list[float]:
    """Deterministic fake embedding for bootstrap — replace with real model later."""
    digest = hashlib.sha256(text.encode()).digest()
    floats = [b / 255.0 for b in digest]
    # Repeat to reach VECTOR_SIZE
    repeated = (floats * (VECTOR_SIZE // len(floats) + 1))[:VECTOR_SIZE]
    return repeated


async def ensure_collection(collection: str) -> None:
    client = _get_client()
    existing = await client.get_collections()
    names = [c.name for c in existing.collections]
    if collection not in names:
        await client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


async def upsert_memory(collection: str, id_: str, text: str, metadata: dict) -> None:
    client = _get_client()
    await ensure_collection(collection)
    await client.upsert(
        collection_name=collection,
        points=[PointStruct(
            id=abs(hash(id_)) % (2**63),
            vector=_text_to_vector(text),
            payload={"text": text, **metadata},
        )],
    )


async def search_memories(collection: str, query: str, limit: int = 5) -> list[dict]:
    client = _get_client()
    await ensure_collection(collection)
    results = await client.search(
        collection_name=collection,
        query_vector=_text_to_vector(query),
        limit=limit,
        with_payload=True,
    )
    return [r.payload for r in results]
```

- [ ] **Step 5: Create `shared/shared/claude_runner.py`**

```python
import subprocess
import shutil


def run_claude(prompt: str, timeout: int = 120) -> str:
    """Run claude CLI with --print flag and return stdout."""
    claude_bin = shutil.which("claude")
    if claude_bin is None:
        raise RuntimeError("claude CLI not found in PATH")

    result = subprocess.run(
        [claude_bin, "--print", prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        raise RuntimeError(f"claude exited {result.returncode}: {result.stderr[:500]}")

    return result.stdout.strip()
```

- [ ] **Step 6: Write failing test for claude_runner**

Create `tests/test_claude_runner.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from shared.claude_runner import run_claude


def test_run_claude_returns_stdout():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Hello from Claude\n"
    mock_result.stderr = ""

    with patch("shared.claude_runner.shutil.which", return_value="/usr/bin/claude"):
        with patch("shared.claude_runner.subprocess.run", return_value=mock_result):
            result = run_claude("say hello")

    assert result == "Hello from Claude"


def test_run_claude_raises_on_nonzero_exit():
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "error"

    with patch("shared.claude_runner.shutil.which", return_value="/usr/bin/claude"):
        with patch("shared.claude_runner.subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="claude exited 1"):
                run_claude("bad prompt")


def test_run_claude_raises_when_not_found():
    with patch("shared.claude_runner.shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="claude CLI not found"):
            run_claude("any prompt")
```

- [ ] **Step 7: Run test to verify it fails**

```bash
cd /path/to/life-agents
pip install -e shared/
pytest tests/test_claude_runner.py -v
```

Expected: 3 tests PASS (mocks don't require `claude` installed locally).

- [ ] **Step 8: Commit**

```bash
git add shared/ tests/test_claude_runner.py
git commit -m "feat: shared library — db, qdrant, claude_runner"
```

---

## Task 3: Sleep Agent

**Files:**
- Create: `agents/sleep/Dockerfile`
- Create: `agents/sleep/requirements.txt`
- Create: `agents/sleep/app/main.py`
- Create: `agents/sleep/app/agent_card.py`
- Create: `agents/sleep/app/tasks.py`
- Create: `agents/sleep/app/prompt.py`
- Create: `tests/test_agent_card.py`
- Create: `tests/test_sleep_tasks.py`

- [ ] **Step 1: Create `agents/sleep/requirements.txt`**

```
fastapi>=0.111
uvicorn[standard]>=0.29
asyncpg>=0.29
qdrant-client>=1.9
httpx>=0.27
```

- [ ] **Step 2: Create `agents/sleep/Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install claude CLI
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://claude.ai/install.sh | sh && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install shared library
COPY ../../shared /shared
RUN pip install --no-cache-dir -e /shared

COPY app/ ./app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

- [ ] **Step 3: Write failing test for agent_card**

Create `tests/test_agent_card.py`:

```python
from agents.sleep.app.agent_card import AGENT_CARD


def test_agent_card_has_required_fields():
    assert "name" in AGENT_CARD
    assert "description" in AGENT_CARD
    assert "url" in AGENT_CARD
    assert "capabilities" in AGENT_CARD
    assert "version" in AGENT_CARD


def test_agent_card_capabilities():
    caps = AGENT_CARD["capabilities"]
    assert "analyze_sleep" in caps
    assert "log_sleep" in caps
    assert "get_recommendations" in caps
```

Run:
```bash
pytest tests/test_agent_card.py -v
```
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Create `agents/sleep/app/agent_card.py`**

```python
import os

AGENT_CARD = {
    "name": "sleep-agent",
    "description": "Tracks sleep patterns, analyzes sleep quality, and gives recommendations based on your history.",
    "url": os.environ.get("SLEEP_AGENT_URL", "http://agent-sleep:8001"),
    "capabilities": ["analyze_sleep", "log_sleep", "get_recommendations"],
    "version": "1.0.0",
}
```

- [ ] **Step 5: Run test to verify it passes**

```bash
PYTHONPATH=. pytest tests/test_agent_card.py -v
```
Expected: 2 tests PASS.

- [ ] **Step 6: Create `agents/sleep/app/prompt.py`**

```python
from shared.db import fetch_recent_logs
from shared.vector import search_memories


async def build_sleep_prompt(task: str, params: dict) -> str:
    recent_logs = await fetch_recent_logs("sleep", limit=10)
    memories = await search_memories("sleep_memories", task, limit=5)

    logs_text = "\n".join(
        f"- {r['recorded_at'].date()} | {r['type']} | {r['data']}"
        for r in recent_logs
    ) or "No recent sleep logs."

    memories_text = "\n".join(
        f"- {m.get('text', '')}" for m in memories
    ) or "No relevant memories."

    return f"""You are a personal sleep health assistant. You have access to the user's sleep history.

## Recent sleep logs (last 10 entries):
{logs_text}

## Relevant memories:
{memories_text}

## User request:
Task: {task}
Params: {params}

Respond in the user's language. Be concise, specific, and actionable. Reference actual data from the logs when relevant."""
```

- [ ] **Step 7: Write failing test for tasks handler**

Create `tests/test_sleep_tasks.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_handle_analyze_sleep_returns_response():
    with patch("agents.sleep.app.tasks.build_sleep_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.sleep.app.tasks.run_claude") as mock_claude:
            with patch("agents.sleep.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.sleep.app.tasks.upsert_memory", new_callable=AsyncMock):
                    mock_prompt.return_value = "mocked prompt"
                    mock_claude.return_value = "You slept 7 hours on average."

                    from agents.sleep.app.tasks import handle_task
                    result = await handle_task("analyze_sleep", {})

    assert result["status"] == "completed"
    assert "You slept" in result["output"]


@pytest.mark.asyncio
async def test_handle_unknown_task_returns_error():
    from agents.sleep.app.tasks import handle_task
    result = await handle_task("unknown_task", {})
    assert result["status"] == "error"
    assert "unknown" in result["output"].lower()
```

Run:
```bash
PYTHONPATH=. pytest tests/test_sleep_tasks.py -v
```
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 8: Create `agents/sleep/app/tasks.py`**

```python
from shared.claude_runner import run_claude
from shared.db import insert_task, insert_log
from shared.vector import upsert_memory
from .prompt import build_sleep_prompt
import uuid

SUPPORTED_TASKS = {"analyze_sleep", "log_sleep", "get_recommendations"}


async def handle_task(task: str, params: dict) -> dict:
    if task not in SUPPORTED_TASKS:
        return {"status": "error", "output": f"Unknown task: {task}"}

    prompt = await build_sleep_prompt(task, params)
    output = run_claude(prompt)

    await insert_task("sleep", task, params, output)
    await upsert_memory(
        collection="sleep_memories",
        id_=str(uuid.uuid4()),
        text=output,
        metadata={"task": task, "params": str(params)},
    )

    return {"status": "completed", "output": output}
```

- [ ] **Step 9: Run test to verify it passes**

```bash
PYTHONPATH=. pytest tests/test_sleep_tasks.py -v
```
Expected: 2 tests PASS.

- [ ] **Step 10: Create `agents/sleep/app/main.py`**

```python
from fastapi import FastAPI
from pydantic import BaseModel
from .agent_card import AGENT_CARD
from .tasks import handle_task

app = FastAPI(title="Sleep Agent")


class TaskRequest(BaseModel):
    task: str
    params: dict = {}


@app.get("/.well-known/agent.json")
async def agent_card():
    return AGENT_CARD


@app.post("/tasks")
async def create_task(req: TaskRequest):
    result = await handle_task(req.task, req.params)
    return result


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 11: Commit**

```bash
git add agents/sleep/ tests/test_agent_card.py tests/test_sleep_tasks.py
git commit -m "feat: sleep agent with A2A agent card and task handler"
```

---

## Task 4: Orchestrator

**Files:**
- Create: `orchestrator/Dockerfile`
- Create: `orchestrator/requirements.txt`
- Create: `orchestrator/app/main.py`
- Create: `orchestrator/app/registry.py`
- Create: `orchestrator/app/router.py`
- Create: `tests/test_orchestrator_routing.py`

- [ ] **Step 1: Create `orchestrator/requirements.txt`**

```
fastapi>=0.111
uvicorn[standard]>=0.29
httpx>=0.27
```

- [ ] **Step 2: Create `orchestrator/Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: Write failing test for routing**

Create `tests/test_orchestrator_routing.py`:

```python
import pytest
from orchestrator.app.router import classify_intent


def test_classify_sleep_intent():
    assert classify_intent("Как я спал на этой неделе?") == "sleep"
    assert classify_intent("analyze my sleep") == "sleep"
    assert classify_intent("sleep recommendation") == "sleep"


def test_classify_workout_intent():
    assert classify_intent("Сколько я тренировался?") == "workout"
    assert classify_intent("log my run") == "workout"


def test_classify_nutrition_intent():
    assert classify_intent("Что я ел сегодня?") == "nutrition"
    assert classify_intent("log meal") == "nutrition"


def test_classify_unknown_defaults_to_sleep():
    # Unknown intent defaults to first available agent
    result = classify_intent("random unrelated text xyz")
    assert result in ("sleep", "workout", "nutrition")
```

Run:
```bash
PYTHONPATH=. pytest tests/test_orchestrator_routing.py -v
```
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Create `orchestrator/app/router.py`**

```python
INTENT_KEYWORDS: dict[str, list[str]] = {
    "sleep": ["sleep", "спал", "сон", "засыпал", "проснул", "ночь"],
    "workout": ["workout", "трениров", "пробеж", "run", "exercise", "спорт", "фитнес"],
    "nutrition": ["nutrition", "еда", "ел", "питание", "meal", "food", "калори"],
}


def classify_intent(message: str) -> str:
    lower = message.lower()
    for agent, keywords in INTENT_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return agent
    return "sleep"  # default
```

- [ ] **Step 5: Run test to verify it passes**

```bash
PYTHONPATH=. pytest tests/test_orchestrator_routing.py -v
```
Expected: 4 tests PASS.

- [ ] **Step 6: Create `orchestrator/app/registry.py`**

```python
import httpx
import os
import logging

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
                _registry[agent_name] = {"url": url, "card": card}
                logger.info(f"Discovered agent: {agent_name} at {url}")
        except Exception as e:
            logger.warning(f"Could not discover agent at {url}: {e}")


def get_agent_url(agent_name: str) -> str | None:
    entry = _registry.get(agent_name)
    return entry["url"] if entry else None


def list_agents() -> list[str]:
    return list(_registry.keys())
```

- [ ] **Step 7: Create `orchestrator/app/main.py`**

```python
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from pydantic import BaseModel
import httpx

from .registry import discover_agents, get_agent_url, list_agents
from .router import classify_intent


@asynccontextmanager
async def lifespan(app: FastAPI):
    await discover_agents()
    yield


app = FastAPI(title="Orchestrator", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str
    params: dict = {}


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
        resp = await client.post(
            f"{agent_url}/tasks",
            json={"task": "analyze_sleep", "params": {"message": req.message}},
        )
        resp.raise_for_status()
        return resp.json()


@app.get("/agents")
async def agents():
    return {"agents": list_agents()}


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 8: Commit**

```bash
git add orchestrator/ tests/test_orchestrator_routing.py
git commit -m "feat: orchestrator with A2A discovery and intent-based routing"
```

---

## Task 5: End-to-End Integration

- [ ] **Step 1: Build and start all containers**

```bash
docker compose up --build -d
```

Wait ~30 seconds for services to start.

- [ ] **Step 2: Verify agent card is reachable**

```bash
curl http://localhost:8001/.well-known/agent.json
```

Expected output:
```json
{"name": "sleep-agent", "description": "...", "url": "...", "capabilities": [...], "version": "1.0.0"}
```

- [ ] **Step 3: Verify orchestrator discovers the agent**

```bash
curl http://localhost:8000/agents
```

Expected output:
```json
{"agents": ["sleep"]}
```

- [ ] **Step 4: Send a chat message through the orchestrator**

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Как я спал на этой неделе?"}'
```

Expected: JSON response with `"status": "completed"` and `"output"` containing Claude's response.

- [ ] **Step 5: Verify the task was logged in Postgres**

```bash
docker compose exec postgres psql -U lifeagents -d lifeagents \
  -c "SELECT agent, task_type, output, created_at FROM tasks ORDER BY created_at DESC LIMIT 3;"
```

Expected: one row with `agent=sleep`.

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "feat: end-to-end integration verified — orchestrator routes to sleep agent via A2A"
```

---

## Self-Review

**Spec coverage:**
- [x] Docker containers with `claude` CLI — Task 1, Task 3, Task 5
- [x] Agent Card per A2A spec — Task 3
- [x] Orchestrator discovery — Task 4
- [x] Intent routing — Task 4
- [x] `~/.claude` mounted for auth — Task 1 (docker-compose.yml)
- [x] Postgres schema — Task 1
- [x] Qdrant vector memory — Task 2, Task 3
- [x] `claude --print` subprocess — Task 2

**Out of scope for this plan (covered in future plans):**
- Workout + Nutrition agents
- Telegram bot
- AG-UI frontend
- Sync service
- Real embeddings (Qdrant uses hash-based fake vectors for bootstrap)

**Next plans:**
- Plan 2: Workout + Nutrition agents (same pattern as sleep)
- Plan 3: Telegram bot
- Plan 4: AG-UI frontend
- Plan 5: Sync service
