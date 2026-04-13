# Workout + Nutrition Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `agent-workout` (port 8002) and `agent-nutrition` (port 8003) to the life-agents system, following the exact pattern of `agent-sleep`, with cross-agent context via shared Postgres reads.

**Architecture:** Each agent is a Python/FastAPI service with `agent_card.py`, `tasks.py`, `prompt.py`, and `main.py`. Both agents read each other's `health_logs` rows when building prompts — no HTTP between agents. Orchestrator picks them up automatically via the `AGENT_URLS` env var.

**Tech Stack:** Python 3.12, FastAPI, asyncpg, qdrant-client, shared library (`shared/`), Claude CLI via `claude_runner.run_claude`, pytest + pytest-asyncio.

---

## File Map

**Create:**
- `agents/workout/__init__.py`
- `agents/workout/Dockerfile`
- `agents/workout/requirements.txt`
- `agents/workout/app/__init__.py`
- `agents/workout/app/agent_card.py`
- `agents/workout/app/main.py`
- `agents/workout/app/tasks.py`
- `agents/workout/app/prompt.py`
- `agents/nutrition/__init__.py`
- `agents/nutrition/Dockerfile`
- `agents/nutrition/requirements.txt`
- `agents/nutrition/app/__init__.py`
- `agents/nutrition/app/agent_card.py`
- `agents/nutrition/app/main.py`
- `agents/nutrition/app/tasks.py`
- `agents/nutrition/app/prompt.py`
- `tests/test_workout_tasks.py`
- `tests/test_nutrition_tasks.py`

**Modify:**
- `tests/test_agent_card.py` — add workout + nutrition card tests
- `docker-compose.yml` — add `agent-workout` and `agent-nutrition` services
- `.env.example` — add `WORKOUT_AGENT_URL`, `NUTRITION_AGENT_URL`

---

## Task 1: Workout agent card

**Files:**
- Create: `agents/workout/__init__.py`
- Create: `agents/workout/app/__init__.py`
- Create: `agents/workout/app/agent_card.py`
- Modify: `tests/test_agent_card.py`

- [ ] **Step 1: Create empty `__init__.py` files**

```bash
touch agents/workout/__init__.py agents/workout/app/__init__.py
```

- [ ] **Step 2: Write failing tests** — append to `tests/test_agent_card.py`:

```python
from agents.workout.app.agent_card import AGENT_CARD as WORKOUT_CARD


def test_workout_agent_card_has_required_fields():
    assert "name" in WORKOUT_CARD
    assert "description" in WORKOUT_CARD
    assert "url" in WORKOUT_CARD
    assert "capabilities" in WORKOUT_CARD
    assert "version" in WORKOUT_CARD


def test_workout_agent_card_capabilities():
    caps = WORKOUT_CARD["capabilities"]
    assert "log_workout" in caps
    assert "analyze_workout" in caps
    assert "get_recommendations" in caps
```

- [ ] **Step 3: Run to confirm failure**

```bash
pytest tests/test_agent_card.py::test_workout_agent_card_has_required_fields -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 4: Create `agents/workout/app/agent_card.py`**

```python
import os

AGENT_CARD = {
    "name": "workout-agent",
    "description": "Tracks workouts (strength, cycling, combat sports), analyzes training load and progress, and gives recommendations based on history and nutrition.",
    "url": os.environ.get("WORKOUT_AGENT_URL", "http://agent-workout:8002"),
    "capabilities": ["log_workout", "analyze_workout", "get_recommendations"],
    "version": "1.0.0",
}
```

- [ ] **Step 5: Run tests to confirm pass**

```bash
pytest tests/test_agent_card.py -v
```

Expected: all existing sleep tests + 2 new workout tests PASS

- [ ] **Step 6: Commit**

```bash
git add agents/workout/__init__.py agents/workout/app/__init__.py agents/workout/app/agent_card.py tests/test_agent_card.py
git commit -m "feat: add workout agent card"
```

---

## Task 2: Workout tasks.py

**Files:**
- Create: `tests/test_workout_tasks.py`
- Create: `agents/workout/app/tasks.py`

- [ ] **Step 1: Create `tests/test_workout_tasks.py`**

```python
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_handle_log_workout_returns_completed():
    with patch("agents.workout.app.tasks.build_workout_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.workout.app.tasks.run_claude") as mock_claude:
            with patch("agents.workout.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.workout.app.tasks.upsert_memory", new_callable=AsyncMock):
                    mock_prompt.return_value = "mocked prompt"
                    mock_claude.return_value = "Workout logged: strength session, 60 min."

                    from agents.workout.app.tasks import handle_task
                    result = await handle_task("log_workout", {"type": "strength", "duration_min": 60})

    assert result["status"] == "completed"
    assert "Workout logged" in result["output"]


@pytest.mark.asyncio
async def test_handle_analyze_workout_returns_completed():
    with patch("agents.workout.app.tasks.build_workout_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.workout.app.tasks.run_claude") as mock_claude:
            with patch("agents.workout.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.workout.app.tasks.upsert_memory", new_callable=AsyncMock):
                    mock_prompt.return_value = "mocked prompt"
                    mock_claude.return_value = "Your training volume increased 15% this week."

                    from agents.workout.app.tasks import handle_task
                    result = await handle_task("analyze_workout", {})

    assert result["status"] == "completed"
    assert "training" in result["output"].lower()


@pytest.mark.asyncio
async def test_handle_get_workout_recommendations_returns_completed():
    with patch("agents.workout.app.tasks.build_workout_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.workout.app.tasks.run_claude") as mock_claude:
            with patch("agents.workout.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.workout.app.tasks.upsert_memory", new_callable=AsyncMock):
                    mock_prompt.return_value = "mocked prompt"
                    mock_claude.return_value = "Rest day recommended based on recent load."

                    from agents.workout.app.tasks import handle_task
                    result = await handle_task("get_recommendations", {})

    assert result["status"] == "completed"
    assert result["output"] == "Rest day recommended based on recent load."


@pytest.mark.asyncio
async def test_handle_unknown_workout_task_returns_error():
    from agents.workout.app.tasks import handle_task
    result = await handle_task("fly_to_moon", {})
    assert result["status"] == "error"
    assert "unknown" in result["output"].lower()
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_workout_tasks.py -v
```

Expected: `ModuleNotFoundError` (tasks.py doesn't exist yet)

- [ ] **Step 3: Create `agents/workout/app/tasks.py`**

```python
import asyncio
import json
import uuid

from shared.claude_runner import run_claude
from shared.db import insert_task
from shared.vector import upsert_memory
from .prompt import build_workout_prompt

SUPPORTED_TASKS = {"log_workout", "analyze_workout", "get_recommendations"}


async def handle_task(task: str, params: dict) -> dict:
    if task not in SUPPORTED_TASKS:
        return {"status": "error", "output": f"Unknown task: {task}"}

    try:
        prompt = await build_workout_prompt(task, params)
        output = await asyncio.to_thread(run_claude, prompt)
        await insert_task("workout", task, params, output)
        await upsert_memory(
            collection="workout_memories",
            id_=str(uuid.uuid4()),
            text=output,
            metadata={"task": task, "params": json.dumps(params)},
        )
        return {"status": "completed", "output": output}
    except Exception as e:
        return {"status": "error", "output": str(e)}
```

- [ ] **Step 4: Create a stub `agents/workout/app/prompt.py`** (needed so `tasks.py` imports don't fail at test time)

```python
async def build_workout_prompt(task: str, params: dict) -> str:
    return f"Task: {task}"
```

- [ ] **Step 5: Run tests to confirm pass**

```bash
pytest tests/test_workout_tasks.py -v
```

Expected: 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add agents/workout/app/tasks.py agents/workout/app/prompt.py tests/test_workout_tasks.py
git commit -m "feat: add workout agent tasks handler"
```

---

## Task 3: Workout prompt.py

**Files:**
- Modify: `agents/workout/app/prompt.py` (replace stub with real implementation)

- [ ] **Step 1: Write prompt tests** — create `tests/test_workout_prompt.py`

```python
import pytest
from unittest.mock import AsyncMock, patch, call


@pytest.mark.asyncio
async def test_build_workout_prompt_contains_task_name():
    with patch("agents.workout.app.prompt.fetch_recent_logs", new_callable=AsyncMock) as mock_logs:
        with patch("agents.workout.app.prompt.search_memories", new_callable=AsyncMock) as mock_mem:
            mock_logs.return_value = []
            mock_mem.return_value = []

            from agents.workout.app.prompt import build_workout_prompt
            result = await build_workout_prompt("analyze_workout", {"message": "how am I doing?"})

    assert "analyze_workout" in result
    assert "workout" in result.lower()


@pytest.mark.asyncio
async def test_build_workout_prompt_queries_both_agents():
    with patch("agents.workout.app.prompt.fetch_recent_logs", new_callable=AsyncMock) as mock_logs:
        with patch("agents.workout.app.prompt.search_memories", new_callable=AsyncMock) as mock_mem:
            mock_logs.return_value = []
            mock_mem.return_value = []

            from agents.workout.app.prompt import build_workout_prompt
            await build_workout_prompt("get_recommendations", {})

    assert mock_logs.call_count == 2
    agents_queried = [c.args[0] for c in mock_logs.call_args_list]
    assert "workout" in agents_queried
    assert "nutrition" in agents_queried


@pytest.mark.asyncio
async def test_build_workout_prompt_shows_no_logs_fallback():
    with patch("agents.workout.app.prompt.fetch_recent_logs", new_callable=AsyncMock) as mock_logs:
        with patch("agents.workout.app.prompt.search_memories", new_callable=AsyncMock) as mock_mem:
            mock_logs.return_value = []
            mock_mem.return_value = []

            from agents.workout.app.prompt import build_workout_prompt
            result = await build_workout_prompt("log_workout", {})

    assert "No recent workout logs" in result
    assert "No recent nutrition logs" in result
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_workout_prompt.py -v
```

Expected: `test_build_workout_prompt_queries_both_agents` FAIL (stub only calls nothing)

- [ ] **Step 3: Replace stub with real `agents/workout/app/prompt.py`**

```python
from shared.db import fetch_recent_logs
from shared.vector import search_memories


async def build_workout_prompt(task: str, params: dict) -> str:
    workout_logs = await fetch_recent_logs("workout", limit=10)
    nutrition_logs = await fetch_recent_logs("nutrition", limit=5)
    memories = await search_memories("workout_memories", task, limit=5)

    workout_text = "\n".join(
        f"- {r['recorded_at'].date()} | {r['type']} | {r['data']}"
        for r in workout_logs
    ) or "No recent workout logs."

    nutrition_text = "\n".join(
        f"- {r['recorded_at'].date()} | {r['type']} | {r['data']}"
        for r in nutrition_logs
    ) or "No recent nutrition logs."

    memories_text = "\n".join(
        f"- {m.get('text', '')}" for m in memories
    ) or "No relevant memories."

    return f"""You are a personal workout and training assistant. You have access to the user's training history and recent nutrition.

## Recent workouts (last 10):
{workout_text}

## Recent nutrition (last 5):
{nutrition_text}

## Relevant memories:
{memories_text}

## User request:
Task: {task}
Params: {params}

Respond in the user's language. Be concise, specific, and actionable. Reference actual data when relevant.
Workout types tracked: strength (exercises/sets/reps/weight_kg), cycling (distance_km/duration_min/avg_hr), combat (discipline: boxing|mma|muay_thai, duration_min, intensity).
For log_workout: confirm what was logged and note any recovery considerations given recent nutrition.
For analyze_workout: identify trends in volume, intensity, and recovery across workout types.
For get_recommendations: suggest next session type and intensity based on recent training load and nutrition intake."""
```

- [ ] **Step 4: Run all workout tests**

```bash
pytest tests/test_workout_tasks.py tests/test_workout_prompt.py tests/test_agent_card.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add agents/workout/app/prompt.py tests/test_workout_prompt.py
git commit -m "feat: add workout agent prompt builder with cross-agent nutrition context"
```

---

## Task 4: Workout main.py + Dockerfile + requirements

**Files:**
- Create: `agents/workout/app/main.py`
- Create: `agents/workout/Dockerfile`
- Create: `agents/workout/requirements.txt`

- [ ] **Step 1: Create `agents/workout/app/main.py`**

```python
from fastapi import FastAPI
from pydantic import BaseModel
from .agent_card import AGENT_CARD
from .tasks import handle_task

app = FastAPI(title="Workout Agent")


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

- [ ] **Step 2: Create `agents/workout/requirements.txt`**

```
fastapi>=0.111
uvicorn[standard]>=0.29
asyncpg>=0.29
qdrant-client>=1.9
httpx>=0.27
```

- [ ] **Step 3: Create `agents/workout/Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install Node.js 22 (via NodeSource) and claude CLI
RUN apt-get update && apt-get install -y curl ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g @anthropic-ai/claude-code && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY agents/workout/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install shared library
COPY shared/ /shared
RUN pip install --no-cache-dir -e /shared

COPY agents/workout/app/ ./app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
```

- [ ] **Step 4: Run full test suite to confirm nothing broken**

```bash
pytest -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add agents/workout/app/main.py agents/workout/requirements.txt agents/workout/Dockerfile
git commit -m "feat: add workout agent FastAPI app and Docker build"
```

---

## Task 5: Nutrition agent card

**Files:**
- Create: `agents/nutrition/__init__.py`
- Create: `agents/nutrition/app/__init__.py`
- Create: `agents/nutrition/app/agent_card.py`
- Modify: `tests/test_agent_card.py`

- [ ] **Step 1: Create empty `__init__.py` files**

```bash
touch agents/nutrition/__init__.py agents/nutrition/app/__init__.py
```

- [ ] **Step 2: Append nutrition card tests to `tests/test_agent_card.py`**

```python
from agents.nutrition.app.agent_card import AGENT_CARD as NUTRITION_CARD


def test_nutrition_agent_card_has_required_fields():
    assert "name" in NUTRITION_CARD
    assert "description" in NUTRITION_CARD
    assert "url" in NUTRITION_CARD
    assert "capabilities" in NUTRITION_CARD
    assert "version" in NUTRITION_CARD


def test_nutrition_agent_card_capabilities():
    caps = NUTRITION_CARD["capabilities"]
    assert "log_meal" in caps
    assert "analyze_nutrition" in caps
    assert "get_recommendations" in caps
```

- [ ] **Step 3: Run to confirm failure**

```bash
pytest tests/test_agent_card.py::test_nutrition_agent_card_has_required_fields -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 4: Create `agents/nutrition/app/agent_card.py`**

```python
import os

AGENT_CARD = {
    "name": "nutrition-agent",
    "description": "Logs meals from free text, parses macros with Claude, analyzes nutrition patterns, and gives recommendations tailored to recent workout load.",
    "url": os.environ.get("NUTRITION_AGENT_URL", "http://agent-nutrition:8003"),
    "capabilities": ["log_meal", "analyze_nutrition", "get_recommendations"],
    "version": "1.0.0",
}
```

- [ ] **Step 5: Run tests to confirm pass**

```bash
pytest tests/test_agent_card.py -v
```

Expected: all 6 card tests PASS

- [ ] **Step 6: Commit**

```bash
git add agents/nutrition/__init__.py agents/nutrition/app/__init__.py agents/nutrition/app/agent_card.py tests/test_agent_card.py
git commit -m "feat: add nutrition agent card"
```

---

## Task 6: Nutrition tasks.py

**Files:**
- Create: `tests/test_nutrition_tasks.py`
- Create: `agents/nutrition/app/tasks.py`

- [ ] **Step 1: Create `tests/test_nutrition_tasks.py`**

```python
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_handle_log_meal_returns_completed():
    with patch("agents.nutrition.app.tasks.build_nutrition_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.nutrition.app.tasks.run_claude") as mock_claude:
            with patch("agents.nutrition.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.nutrition.app.tasks.upsert_memory", new_callable=AsyncMock):
                    mock_prompt.return_value = "mocked prompt"
                    mock_claude.return_value = "Meal logged: гречка с курицей ~520 ккал, 42г белка."

                    from agents.nutrition.app.tasks import handle_task
                    result = await handle_task("log_meal", {"raw_text": "гречка с курицей"})

    assert result["status"] == "completed"
    assert "Meal logged" in result["output"]


@pytest.mark.asyncio
async def test_handle_log_meal_passes_raw_text_in_params():
    with patch("agents.nutrition.app.tasks.build_nutrition_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.nutrition.app.tasks.run_claude") as mock_claude:
            with patch("agents.nutrition.app.tasks.insert_task", new_callable=AsyncMock) as mock_insert:
                with patch("agents.nutrition.app.tasks.upsert_memory", new_callable=AsyncMock):
                    mock_prompt.return_value = "mocked prompt"
                    mock_claude.return_value = "Logged."

                    from agents.nutrition.app.tasks import handle_task
                    await handle_task("log_meal", {"raw_text": "творог с бананом"})

    # insert_task is called with the original params including raw_text
    call_kwargs = mock_insert.call_args
    assert call_kwargs.args[2].get("raw_text") == "творог с бананом"


@pytest.mark.asyncio
async def test_handle_analyze_nutrition_returns_completed():
    with patch("agents.nutrition.app.tasks.build_nutrition_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.nutrition.app.tasks.run_claude") as mock_claude:
            with patch("agents.nutrition.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.nutrition.app.tasks.upsert_memory", new_callable=AsyncMock):
                    mock_prompt.return_value = "mocked prompt"
                    mock_claude.return_value = "Your average protein intake is 120g/day."

                    from agents.nutrition.app.tasks import handle_task
                    result = await handle_task("analyze_nutrition", {})

    assert result["status"] == "completed"
    assert "protein" in result["output"].lower()


@pytest.mark.asyncio
async def test_handle_get_nutrition_recommendations_returns_completed():
    with patch("agents.nutrition.app.tasks.build_nutrition_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.nutrition.app.tasks.run_claude") as mock_claude:
            with patch("agents.nutrition.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.nutrition.app.tasks.upsert_memory", new_callable=AsyncMock):
                    mock_prompt.return_value = "mocked prompt"
                    mock_claude.return_value = "Increase protein to 160g today — heavy leg day yesterday."

                    from agents.nutrition.app.tasks import handle_task
                    result = await handle_task("get_recommendations", {})

    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_handle_unknown_nutrition_task_returns_error():
    from agents.nutrition.app.tasks import handle_task
    result = await handle_task("order_pizza", {})
    assert result["status"] == "error"
    assert "unknown" in result["output"].lower()
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_nutrition_tasks.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create stub `agents/nutrition/app/prompt.py`**

```python
async def build_nutrition_prompt(task: str, params: dict) -> str:
    return f"Task: {task}"
```

- [ ] **Step 4: Create `agents/nutrition/app/tasks.py`**

```python
import asyncio
import json
import uuid

from shared.claude_runner import run_claude
from shared.db import insert_task
from shared.vector import upsert_memory
from .prompt import build_nutrition_prompt

SUPPORTED_TASKS = {"log_meal", "analyze_nutrition", "get_recommendations"}


async def handle_task(task: str, params: dict) -> dict:
    if task not in SUPPORTED_TASKS:
        return {"status": "error", "output": f"Unknown task: {task}"}

    try:
        prompt = await build_nutrition_prompt(task, params)
        output = await asyncio.to_thread(run_claude, prompt)
        await insert_task("nutrition", task, params, output)
        await upsert_memory(
            collection="nutrition_memories",
            id_=str(uuid.uuid4()),
            text=output,
            metadata={"task": task, "params": json.dumps(params)},
        )
        return {"status": "completed", "output": output}
    except Exception as e:
        return {"status": "error", "output": str(e)}
```

- [ ] **Step 5: Run tests to confirm pass**

```bash
pytest tests/test_nutrition_tasks.py -v
```

Expected: 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add agents/nutrition/app/tasks.py agents/nutrition/app/prompt.py tests/test_nutrition_tasks.py
git commit -m "feat: add nutrition agent tasks handler"
```

---

## Task 7: Nutrition prompt.py

**Files:**
- Modify: `agents/nutrition/app/prompt.py` (replace stub)

- [ ] **Step 1: Create `tests/test_nutrition_prompt.py`**

```python
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_build_nutrition_prompt_contains_task_name():
    with patch("agents.nutrition.app.prompt.fetch_recent_logs", new_callable=AsyncMock) as mock_logs:
        with patch("agents.nutrition.app.prompt.search_memories", new_callable=AsyncMock) as mock_mem:
            mock_logs.return_value = []
            mock_mem.return_value = []

            from agents.nutrition.app.prompt import build_nutrition_prompt
            result = await build_nutrition_prompt("log_meal", {"raw_text": "овсянка"})

    assert "log_meal" in result
    assert "nutrition" in result.lower()


@pytest.mark.asyncio
async def test_build_nutrition_prompt_queries_both_agents():
    with patch("agents.nutrition.app.prompt.fetch_recent_logs", new_callable=AsyncMock) as mock_logs:
        with patch("agents.nutrition.app.prompt.search_memories", new_callable=AsyncMock) as mock_mem:
            mock_logs.return_value = []
            mock_mem.return_value = []

            from agents.nutrition.app.prompt import build_nutrition_prompt
            await build_nutrition_prompt("get_recommendations", {})

    assert mock_logs.call_count == 2
    agents_queried = [c.args[0] for c in mock_logs.call_args_list]
    assert "nutrition" in agents_queried
    assert "workout" in agents_queried


@pytest.mark.asyncio
async def test_build_nutrition_prompt_shows_no_logs_fallback():
    with patch("agents.nutrition.app.prompt.fetch_recent_logs", new_callable=AsyncMock) as mock_logs:
        with patch("agents.nutrition.app.prompt.search_memories", new_callable=AsyncMock) as mock_mem:
            mock_logs.return_value = []
            mock_mem.return_value = []

            from agents.nutrition.app.prompt import build_nutrition_prompt
            result = await build_nutrition_prompt("analyze_nutrition", {})

    assert "No recent nutrition logs" in result
    assert "No recent workout logs" in result


@pytest.mark.asyncio
async def test_build_nutrition_prompt_includes_raw_text_in_params():
    with patch("agents.nutrition.app.prompt.fetch_recent_logs", new_callable=AsyncMock) as mock_logs:
        with patch("agents.nutrition.app.prompt.search_memories", new_callable=AsyncMock) as mock_mem:
            mock_logs.return_value = []
            mock_mem.return_value = []

            from agents.nutrition.app.prompt import build_nutrition_prompt
            result = await build_nutrition_prompt("log_meal", {"raw_text": "греческий йогурт"})

    assert "греческий йогурт" in result
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_nutrition_prompt.py -v
```

Expected: `test_build_nutrition_prompt_queries_both_agents` and `test_build_nutrition_prompt_includes_raw_text_in_params` FAIL

- [ ] **Step 3: Replace stub with real `agents/nutrition/app/prompt.py`**

```python
from shared.db import fetch_recent_logs
from shared.vector import search_memories


async def build_nutrition_prompt(task: str, params: dict) -> str:
    nutrition_logs = await fetch_recent_logs("nutrition", limit=10)
    workout_logs = await fetch_recent_logs("workout", limit=3)
    memories = await search_memories("nutrition_memories", task, limit=5)

    nutrition_text = "\n".join(
        f"- {r['recorded_at'].date()} | {r['type']} | {r['data']}"
        for r in nutrition_logs
    ) or "No recent nutrition logs."

    workout_text = "\n".join(
        f"- {r['recorded_at'].date()} | {r['type']} | {r['data']}"
        for r in workout_logs
    ) or "No recent workout logs."

    memories_text = "\n".join(
        f"- {m.get('text', '')}" for m in memories
    ) or "No relevant memories."

    return f"""You are a personal nutrition assistant. You have access to the user's meal history and recent workouts.

## Recent nutrition (last 10 meals):
{nutrition_text}

## Recent workouts (last 3):
{workout_text}

## Relevant memories:
{memories_text}

## User request:
Task: {task}
Params: {params}

Respond in the user's language. Be concise, specific, and actionable. Reference actual data when relevant.
For log_meal: parse the free-text meal description from params['raw_text'], estimate КБЖУ (kcal, protein_g, carbs_g, fat_g), and confirm what was logged. If uncertain about macros, state your confidence level.
For analyze_nutrition: identify trends in daily calories, protein intake, and meal timing relative to workouts.
For get_recommendations: suggest nutrition adjustments based on recent workout intensity and current macro balance. Flag low protein on training days."""
```

- [ ] **Step 4: Run all nutrition tests**

```bash
pytest tests/test_nutrition_tasks.py tests/test_nutrition_prompt.py tests/test_agent_card.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add agents/nutrition/app/prompt.py tests/test_nutrition_prompt.py
git commit -m "feat: add nutrition agent prompt builder with cross-agent workout context"
```

---

## Task 8: Nutrition main.py + Dockerfile + requirements

**Files:**
- Create: `agents/nutrition/app/main.py`
- Create: `agents/nutrition/Dockerfile`
- Create: `agents/nutrition/requirements.txt`

- [ ] **Step 1: Create `agents/nutrition/app/main.py`**

```python
from fastapi import FastAPI
from pydantic import BaseModel
from .agent_card import AGENT_CARD
from .tasks import handle_task

app = FastAPI(title="Nutrition Agent")


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

- [ ] **Step 2: Create `agents/nutrition/requirements.txt`**

```
fastapi>=0.111
uvicorn[standard]>=0.29
asyncpg>=0.29
qdrant-client>=1.9
httpx>=0.27
```

- [ ] **Step 3: Create `agents/nutrition/Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install Node.js 22 (via NodeSource) and claude CLI
RUN apt-get update && apt-get install -y curl ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g @anthropic-ai/claude-code && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY agents/nutrition/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install shared library
COPY shared/ /shared
RUN pip install --no-cache-dir -e /shared

COPY agents/nutrition/app/ ./app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
```

- [ ] **Step 4: Run full test suite**

```bash
pytest -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add agents/nutrition/app/main.py agents/nutrition/requirements.txt agents/nutrition/Dockerfile
git commit -m "feat: add nutrition agent FastAPI app and Docker build"
```

---

## Task 9: docker-compose.yml + .env.example

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`

- [ ] **Step 1: Add two new services to `docker-compose.yml`**

Add the following after the `agent-sleep` service block (before `orchestrator`):

```yaml
  agent-workout:
    build:
      context: .
      dockerfile: agents/workout/Dockerfile
    env_file:
      - .env
      - .env.auth
    environment:
      POSTGRES_DSN: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      QDRANT_HOST: ${QDRANT_HOST}
      QDRANT_PORT: ${QDRANT_PORT}
    volumes:
      - ~/.claude:/root/.claude:ro
      - ~/.claude.json:/root/.claude.json:ro
    ports:
      - "8002:8002"
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8002/health"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

  agent-nutrition:
    build:
      context: .
      dockerfile: agents/nutrition/Dockerfile
    env_file:
      - .env
      - .env.auth
    environment:
      POSTGRES_DSN: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      QDRANT_HOST: ${QDRANT_HOST}
      QDRANT_PORT: ${QDRANT_PORT}
    volumes:
      - ~/.claude:/root/.claude:ro
      - ~/.claude.json:/root/.claude.json:ro
    ports:
      - "8003:8003"
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8003/health"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
```

- [ ] **Step 2: Update `orchestrator` service in `docker-compose.yml`** — extend `AGENT_URLS` and add dependencies:

Replace the orchestrator service block:

```yaml
  orchestrator:
    build: ./orchestrator
    environment:
      POSTGRES_DSN: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      AGENT_URLS: "http://agent-sleep:8001,http://agent-workout:8002,http://agent-nutrition:8003"
    ports:
      - "8000:8000"
    depends_on:
      agent-sleep:
        condition: service_healthy
      agent-workout:
        condition: service_healthy
      agent-nutrition:
        condition: service_healthy
```

- [ ] **Step 3: Update `.env.example`** — add new agent URLs:

Append to `.env.example`:

```
WORKOUT_AGENT_URL=http://agent-workout:8002
NUTRITION_AGENT_URL=http://agent-nutrition:8003
```

- [ ] **Step 4: Validate docker-compose config**

```bash
docker compose config --quiet && echo "Config valid"
```

Expected: `Config valid` with no errors

- [ ] **Step 5: Run full test suite one final time**

```bash
pytest -v
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "feat: add workout and nutrition agents to docker-compose"
```

---

## Smoke Test (after `docker compose up`)

After running `scripts/export-auth.sh` and `docker compose up --build`:

```bash
# Verify agents are discovered
curl -s http://localhost:8000/agents | python3 -m json.tool
# Expected: {"agents": ["sleep", "workout", "nutrition"]}

# Test workout agent directly
curl -s -X POST http://localhost:8002/tasks \
  -H "Content-Type: application/json" \
  -d '{"task": "log_workout", "params": {"type": "strength", "exercises": [{"name": "bench press", "sets": 4, "reps": 8, "weight_kg": 80}], "duration_min": 60, "feeling": "good"}}' \
  | python3 -m json.tool
# Expected: {"status": "completed", "output": "..."}

# Test nutrition agent directly
curl -s -X POST http://localhost:8003/tasks \
  -H "Content-Type: application/json" \
  -d '{"task": "log_meal", "params": {"raw_text": "гречка с курицей и салат", "meal_type": "lunch"}}' \
  | python3 -m json.tool
# Expected: {"status": "completed", "output": "..."}

# Test cross-agent routing via orchestrator
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "посоветуй что поесть после сегодняшней тренировки"}' \
  | python3 -m json.tool
# Expected: {"status": "completed", "output": "..."}  (routed to nutrition agent)
```
