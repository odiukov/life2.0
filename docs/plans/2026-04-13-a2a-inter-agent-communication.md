# A2A Inter-Agent Communication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Google A2A protocol so the workout agent calls sleep/nutrition agents as A2A sub-tasks, collects their Artifacts, and returns a single grouped response — with live agent communication state visible in the chat UI.

**Architecture:** Orchestrator determines primary agent, injects peer agent URLs via `peer_agents` in task params. Primary agent calls peers in parallel via `POST /tasks`, collects Artifacts, synthesizes grouped response. All agents expose A2A-compliant Task/Artifact structures and `POST /tasks/stream` SSE endpoints. Orchestrator proxies streaming events to frontend as AG-UI deltas, including status messages showing peer calls in progress.

**Tech Stack:** FastAPI, httpx (already available), Pydantic v2, SSE via StreamingResponse, AG-UI protocol events.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `shared/shared/a2a.py` | **Create** | A2A Pydantic models: `TaskStatus`, `Artifact`, `TextPart`, `A2ATask`, `A2ATaskRequest` |
| `agents/sleep/app/agent_card.py` | **Modify** | Add `capabilities` dict + `skills` list |
| `agents/workout/app/agent_card.py` | **Modify** | Same |
| `agents/nutrition/app/agent_card.py` | **Modify** | Same |
| `agents/sleep/app/tasks.py` | **Modify** | Return `A2ATask`; add push notification webhook |
| `agents/sleep/app/main.py` | **Modify** | Use `A2ATaskRequest`; add `POST /tasks/stream` |
| `agents/nutrition/app/tasks.py` | **Modify** | Same as sleep |
| `agents/nutrition/app/main.py` | **Modify** | Same as sleep |
| `agents/workout/app/prompt.py` | **Modify** | Accept `peer_artifacts` dict; remove passive nutrition DB fetch |
| `agents/workout/app/tasks.py` | **Modify** | `fetch_peer_artifacts` helper; return `A2ATask`; accept `peer_artifacts` kwarg |
| `agents/workout/app/main.py` | **Modify** | Use `A2ATaskRequest`; add `POST /tasks/stream` with peer streaming |
| `orchestrator/app/main.py` | **Modify** | `_build_peer_agents` helper; inject peers in task request; proxy `/tasks/stream` with AG-UI status events |
| `tests/test_a2a_models.py` | **Create** | Tests for A2A model serialization |
| `tests/test_agent_card.py` | **Modify** | Update capability assertions for new schema |
| `tests/test_sleep_tasks.py` | **Modify** | Assert `result.status.state` and `result.artifacts[0].parts[0].text` |
| `tests/test_nutrition_tasks.py` | **Modify** | Same |
| `tests/test_workout_tasks.py` | **Modify** | Same + add peer artifact injection test |
| `tests/test_workout_prompt.py` | **Modify** | Update DB call count assertion; add peer_artifacts test |
| `tests/test_orchestrator_stream.py` | **Modify** | Mock A2A `/tasks/stream` response |

---

## Task 1: A2A Shared Models

**Files:**
- Create: `shared/shared/a2a.py`
- Create: `tests/test_a2a_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_a2a_models.py
from shared.a2a import A2ATask, A2ATaskRequest, TaskStatus, Artifact, TextPart


def test_task_status_now():
    status = TaskStatus.now("completed")
    assert status.state == "completed"
    assert status.timestamp != ""


def test_a2a_task_serializes():
    task = A2ATask(
        id="test-id",
        status=TaskStatus.now("completed"),
        artifacts=[Artifact(name="result", parts=[TextPart(text="hello")])]
    )
    d = task.model_dump()
    assert d["id"] == "test-id"
    assert d["status"]["state"] == "completed"
    assert d["artifacts"][0]["parts"][0]["text"] == "hello"
    assert d["artifacts"][0]["parts"][0]["type"] == "text"


def test_a2a_task_request_defaults():
    req = A2ATaskRequest(task="analyze_sleep")
    assert req.task == "analyze_sleep"
    assert req.params == {}
    assert req.id == ""


def test_task_status_states():
    for state in ("submitted", "working", "completed", "failed"):
        s = TaskStatus.now(state)
        assert s.state == state
```

- [ ] **Step 2: Run test to verify it fails**

```
cd /Users/oleksandr/Documents/life-agents
pytest tests/test_a2a_models.py -v
```
Expected: `ImportError` — `shared.a2a` doesn't exist yet.

- [ ] **Step 3: Create `shared/shared/a2a.py`**

```python
# shared/shared/a2a.py
from pydantic import BaseModel
from typing import Literal
from datetime import datetime, timezone


class TaskStatus(BaseModel):
    state: Literal["submitted", "working", "completed", "failed"]
    timestamp: str = ""

    @classmethod
    def now(cls, state: str) -> "TaskStatus":
        return cls(state=state, timestamp=datetime.now(timezone.utc).isoformat())


class TextPart(BaseModel):
    type: Literal["text"] = "text"
    text: str


class Artifact(BaseModel):
    name: str
    parts: list[TextPart]


class A2ATask(BaseModel):
    id: str
    status: TaskStatus
    artifacts: list[Artifact] = []


class A2ATaskRequest(BaseModel):
    id: str = ""
    task: str
    params: dict = {}
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_a2a_models.py -v
```
Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add shared/shared/a2a.py tests/test_a2a_models.py
git commit -m "feat: add A2A shared Pydantic models"
```

---

## Task 2: A2A-Compliant Agent Cards

**Files:**
- Modify: `agents/sleep/app/agent_card.py`
- Modify: `agents/workout/app/agent_card.py`
- Modify: `agents/nutrition/app/agent_card.py`
- Modify: `tests/test_agent_card.py`

- [ ] **Step 1: Update `tests/test_agent_card.py`**

Replace the file entirely:

```python
# tests/test_agent_card.py
from agents.sleep.app.agent_card import AGENT_CARD
from agents.workout.app.agent_card import AGENT_CARD as WORKOUT_CARD
from agents.nutrition.app.agent_card import AGENT_CARD as NUTRITION_CARD


def test_agent_card_has_required_fields():
    for card in (AGENT_CARD, WORKOUT_CARD, NUTRITION_CARD):
        assert "name" in card
        assert "description" in card
        assert "url" in card
        assert "capabilities" in card
        assert "version" in card
        assert "skills" in card


def test_agent_card_capabilities_a2a():
    for card in (AGENT_CARD, WORKOUT_CARD, NUTRITION_CARD):
        caps = card["capabilities"]
        assert caps["streaming"] is True
        assert caps["pushNotifications"] is True


def test_sleep_agent_card_skills():
    skill_ids = [s["id"] for s in AGENT_CARD["skills"]]
    assert "analyze_sleep" in skill_ids
    assert "log_sleep" in skill_ids
    assert "get_recommendations" in skill_ids


def test_workout_agent_card_skills():
    skill_ids = [s["id"] for s in WORKOUT_CARD["skills"]]
    assert "log_workout" in skill_ids
    assert "analyze_workout" in skill_ids
    assert "get_recommendations" in skill_ids


def test_nutrition_agent_card_skills():
    skill_ids = [s["id"] for s in NUTRITION_CARD["skills"]]
    assert "log_meal" in skill_ids
    assert "analyze_nutrition" in skill_ids
    assert "get_recommendations" in skill_ids
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_agent_card.py -v
```
Expected: FAILED — `capabilities` is a list, `skills` doesn't exist yet.

- [ ] **Step 3: Update all three agent cards**

```python
# agents/sleep/app/agent_card.py
import os

AGENT_CARD = {
    "name": "sleep-agent",
    "description": "Tracks sleep patterns, analyzes sleep quality, and gives recommendations based on your history.",
    "url": os.environ.get("SLEEP_AGENT_URL", "http://agent-sleep:8001"),
    "version": "1.0.0",
    "capabilities": {"streaming": True, "pushNotifications": True},
    "skills": [
        {"id": "analyze_sleep", "name": "Analyze Sleep", "description": "Analyze sleep quality and patterns", "inputModes": ["text"], "outputModes": ["text"]},
        {"id": "log_sleep", "name": "Log Sleep", "description": "Log a new sleep entry", "inputModes": ["text"], "outputModes": ["text"]},
        {"id": "get_recommendations", "name": "Get Recommendations", "description": "Get sleep improvement recommendations", "inputModes": ["text"], "outputModes": ["text"]},
    ],
}
```

```python
# agents/workout/app/agent_card.py
import os

AGENT_CARD = {
    "name": "workout-agent",
    "description": "Tracks workouts (strength, cycling, combat sports), analyzes training load and progress, and gives recommendations based on history and nutrition.",
    "url": os.environ.get("WORKOUT_AGENT_URL", "http://agent-workout:8002"),
    "version": "1.0.0",
    "capabilities": {"streaming": True, "pushNotifications": True},
    "skills": [
        {"id": "log_workout", "name": "Log Workout", "description": "Log a new workout session", "inputModes": ["text"], "outputModes": ["text"]},
        {"id": "analyze_workout", "name": "Analyze Workout", "description": "Analyze training load, trends, and recovery", "inputModes": ["text"], "outputModes": ["text"]},
        {"id": "get_recommendations", "name": "Get Recommendations", "description": "Recommend next session based on history and context", "inputModes": ["text"], "outputModes": ["text"]},
    ],
}
```

```python
# agents/nutrition/app/agent_card.py
import os

AGENT_CARD = {
    "name": "nutrition-agent",
    "description": "Logs meals from free text, parses macros with Claude, analyzes nutrition patterns, and gives recommendations tailored to recent workout load.",
    "url": os.environ.get("NUTRITION_AGENT_URL", "http://agent-nutrition:8003"),
    "version": "1.0.0",
    "capabilities": {"streaming": True, "pushNotifications": True},
    "skills": [
        {"id": "log_meal", "name": "Log Meal", "description": "Log a meal from free text and estimate macros", "inputModes": ["text"], "outputModes": ["text"]},
        {"id": "analyze_nutrition", "name": "Analyze Nutrition", "description": "Analyze nutrition patterns and macro trends", "inputModes": ["text"], "outputModes": ["text"]},
        {"id": "get_recommendations", "name": "Get Recommendations", "description": "Get nutrition recommendations based on recent workout load", "inputModes": ["text"], "outputModes": ["text"]},
    ],
}
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_agent_card.py -v
```
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add agents/sleep/app/agent_card.py agents/workout/app/agent_card.py agents/nutrition/app/agent_card.py tests/test_agent_card.py
git commit -m "feat: update agent cards to A2A format with capabilities and skills"
```

---

## Task 3: Sleep Agent A2A Contract

**Files:**
- Modify: `agents/sleep/app/tasks.py`
- Modify: `agents/sleep/app/main.py`
- Modify: `tests/test_sleep_tasks.py`

- [ ] **Step 1: Update `tests/test_sleep_tasks.py`**

```python
# tests/test_sleep_tasks.py
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_handle_analyze_sleep_returns_completed():
    with patch("agents.sleep.app.tasks.build_sleep_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.sleep.app.tasks.run_claude") as mock_claude:
            with patch("agents.sleep.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.sleep.app.tasks.upsert_memory", new_callable=AsyncMock):
                    mock_prompt.return_value = "mocked prompt"
                    mock_claude.return_value = "You slept 7 hours on average."

                    from agents.sleep.app.tasks import handle_task
                    result = await handle_task("analyze_sleep", {})

    assert result.status.state == "completed"
    assert "You slept" in result.artifacts[0].parts[0].text


@pytest.mark.asyncio
async def test_handle_unknown_task_returns_failed():
    from agents.sleep.app.tasks import handle_task
    result = await handle_task("unknown_task", {})
    assert result.status.state == "failed"
    assert "Unknown task" in result.artifacts[0].parts[0].text


@pytest.mark.asyncio
async def test_handle_sleep_task_has_artifact_name():
    with patch("agents.sleep.app.tasks.build_sleep_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.sleep.app.tasks.run_claude") as mock_claude:
            with patch("agents.sleep.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.sleep.app.tasks.upsert_memory", new_callable=AsyncMock):
                    mock_prompt.return_value = "mocked"
                    mock_claude.return_value = "analysis result"

                    from agents.sleep.app.tasks import handle_task
                    result = await handle_task("log_sleep", {})

    assert result.artifacts[0].name == "analysis"
    assert result.id != ""
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_sleep_tasks.py -v
```
Expected: FAILED — `result["status"]` raises `TypeError` on `A2ATask` object... actually it'll pass `result["status"]` because Pydantic models don't support `[]` access. Error: `TypeError: 'A2ATask' object is not subscriptable`.

- [ ] **Step 3: Update `agents/sleep/app/tasks.py`**

```python
# agents/sleep/app/tasks.py
import asyncio
import json
import logging
import uuid

import httpx

from shared.a2a import A2ATask, Artifact, TaskStatus, TextPart
from shared.claude_runner import run_claude
from shared.db import insert_task
from shared.vector import upsert_memory
from .prompt import build_sleep_prompt

logger = logging.getLogger(__name__)

SUPPORTED_TASKS = {"analyze_sleep", "log_sleep", "get_recommendations"}


async def handle_task(task: str, params: dict) -> A2ATask:
    task_id = str(uuid.uuid4())

    if task not in SUPPORTED_TASKS:
        return A2ATask(
            id=task_id,
            status=TaskStatus.now("failed"),
            artifacts=[Artifact(name="error", parts=[TextPart(text=f"Unknown task: {task}")])],
        )

    try:
        prompt = await build_sleep_prompt(task, params)
        output = await asyncio.to_thread(run_claude, prompt)
        await insert_task("sleep", task, params, output)
        await upsert_memory(
            collection="sleep_memories",
            id_=str(uuid.uuid4()),
            text=output,
            metadata={"task": task, "params": json.dumps(params)},
        )

        result = A2ATask(
            id=task_id,
            status=TaskStatus.now("completed"),
            artifacts=[Artifact(name="analysis", parts=[TextPart(text=output)])],
        )

        webhook_url = params.get("webhook_url")
        if webhook_url:
            asyncio.create_task(_send_webhook(webhook_url, result.model_dump()))

        return result
    except Exception as e:
        return A2ATask(
            id=task_id,
            status=TaskStatus.now("failed"),
            artifacts=[Artifact(name="error", parts=[TextPart(text=str(e))])],
        )


async def _send_webhook(url: str, payload: dict) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=payload)
    except Exception as e:
        logger.warning("Webhook delivery failed to %s: %s", url, e)
```

- [ ] **Step 4: Update `agents/sleep/app/main.py`**

```python
# agents/sleep/app/main.py
import json
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from shared.a2a import A2ATaskRequest
from .agent_card import AGENT_CARD
from .tasks import handle_task

app = FastAPI(title="Sleep Agent")


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@app.get("/.well-known/agent.json")
async def agent_card():
    return AGENT_CARD


@app.post("/tasks")
async def create_task(req: A2ATaskRequest):
    return await handle_task(req.task, req.params)


@app.post("/tasks/stream")
async def stream_task(req: A2ATaskRequest):
    task_id = req.id or str(uuid.uuid4())

    async def generate():
        ts = lambda: datetime.now(timezone.utc).isoformat()
        yield _sse({"id": task_id, "status": {"state": "submitted", "timestamp": ts()}})
        yield _sse({"id": task_id, "status": {"state": "working", "timestamp": ts()}})
        result = await handle_task(req.task, req.params)
        yield _sse(result.model_dump())

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_sleep_tasks.py -v
```
Expected: 3 PASSED.

- [ ] **Step 6: Commit**

```bash
git add agents/sleep/app/tasks.py agents/sleep/app/main.py tests/test_sleep_tasks.py
git commit -m "feat: sleep agent A2A task contract with streaming and webhook support"
```

---

## Task 4: Nutrition Agent A2A Contract

**Files:**
- Modify: `agents/nutrition/app/tasks.py`
- Modify: `agents/nutrition/app/main.py`
- Modify: `tests/test_nutrition_tasks.py`

- [ ] **Step 1: Update `tests/test_nutrition_tasks.py`**

```python
# tests/test_nutrition_tasks.py
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

    assert result.status.state == "completed"
    assert "Meal logged" in result.artifacts[0].parts[0].text


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

    assert mock_insert.call_args.args[2].get("raw_text") == "творог с бананом"


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

    assert result.status.state == "completed"
    assert "protein" in result.artifacts[0].parts[0].text.lower()


@pytest.mark.asyncio
async def test_handle_unknown_nutrition_task_returns_failed():
    from agents.nutrition.app.tasks import handle_task
    result = await handle_task("order_pizza", {})
    assert result.status.state == "failed"
    assert "Unknown task" in result.artifacts[0].parts[0].text
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_nutrition_tasks.py -v
```
Expected: FAILED — `result["status"]` raises `TypeError`.

- [ ] **Step 3: Update `agents/nutrition/app/tasks.py`**

```python
# agents/nutrition/app/tasks.py
import asyncio
import json
import logging
import uuid

import httpx

from shared.a2a import A2ATask, Artifact, TaskStatus, TextPart
from shared.claude_runner import run_claude
from shared.db import insert_task
from shared.vector import upsert_memory
from .prompt import build_nutrition_prompt

logger = logging.getLogger(__name__)

SUPPORTED_TASKS = {"log_meal", "analyze_nutrition", "get_recommendations"}


async def handle_task(task: str, params: dict) -> A2ATask:
    task_id = str(uuid.uuid4())

    if task not in SUPPORTED_TASKS:
        return A2ATask(
            id=task_id,
            status=TaskStatus.now("failed"),
            artifacts=[Artifact(name="error", parts=[TextPart(text=f"Unknown task: {task}")])],
        )

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

        result = A2ATask(
            id=task_id,
            status=TaskStatus.now("completed"),
            artifacts=[Artifact(name="analysis", parts=[TextPart(text=output)])],
        )

        webhook_url = params.get("webhook_url")
        if webhook_url:
            asyncio.create_task(_send_webhook(webhook_url, result.model_dump()))

        return result
    except Exception as e:
        return A2ATask(
            id=task_id,
            status=TaskStatus.now("failed"),
            artifacts=[Artifact(name="error", parts=[TextPart(text=str(e))])],
        )


async def _send_webhook(url: str, payload: dict) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=payload)
    except Exception as e:
        logger.warning("Webhook delivery failed to %s: %s", url, e)
```

- [ ] **Step 4: Update `agents/nutrition/app/main.py`**

```python
# agents/nutrition/app/main.py
import json
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from shared.a2a import A2ATaskRequest
from .agent_card import AGENT_CARD
from .tasks import handle_task

app = FastAPI(title="Nutrition Agent")


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@app.get("/.well-known/agent.json")
async def agent_card():
    return AGENT_CARD


@app.post("/tasks")
async def create_task(req: A2ATaskRequest):
    return await handle_task(req.task, req.params)


@app.post("/tasks/stream")
async def stream_task(req: A2ATaskRequest):
    task_id = req.id or str(uuid.uuid4())

    async def generate():
        ts = lambda: datetime.now(timezone.utc).isoformat()
        yield _sse({"id": task_id, "status": {"state": "submitted", "timestamp": ts()}})
        yield _sse({"id": task_id, "status": {"state": "working", "timestamp": ts()}})
        result = await handle_task(req.task, req.params)
        yield _sse(result.model_dump())

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_nutrition_tasks.py -v
```
Expected: 4 PASSED.

- [ ] **Step 6: Commit**

```bash
git add agents/nutrition/app/tasks.py agents/nutrition/app/main.py tests/test_nutrition_tasks.py
git commit -m "feat: nutrition agent A2A task contract with streaming and webhook support"
```

---

## Task 5: Workout Prompt — Accept Peer Artifacts

**Files:**
- Modify: `agents/workout/app/prompt.py`
- Modify: `tests/test_workout_prompt.py`

- [ ] **Step 1: Update `tests/test_workout_prompt.py`**

```python
# tests/test_workout_prompt.py
import pytest
from unittest.mock import AsyncMock, patch


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
async def test_build_workout_prompt_queries_only_workout_logs():
    """Workout prompt only queries its own DB logs; nutrition comes from peer_artifacts."""
    with patch("agents.workout.app.prompt.fetch_recent_logs", new_callable=AsyncMock) as mock_logs:
        with patch("agents.workout.app.prompt.search_memories", new_callable=AsyncMock) as mock_mem:
            mock_logs.return_value = []
            mock_mem.return_value = []

            from agents.workout.app.prompt import build_workout_prompt
            await build_workout_prompt("get_recommendations", {})

    assert mock_logs.call_count == 1
    assert mock_logs.call_args.args[0] == "workout"


@pytest.mark.asyncio
async def test_build_workout_prompt_includes_peer_artifacts():
    with patch("agents.workout.app.prompt.fetch_recent_logs", new_callable=AsyncMock) as mock_logs:
        with patch("agents.workout.app.prompt.search_memories", new_callable=AsyncMock) as mock_mem:
            mock_logs.return_value = []
            mock_mem.return_value = []

            from agents.workout.app.prompt import build_workout_prompt
            result = await build_workout_prompt(
                "get_recommendations",
                {},
                peer_artifacts={"sleep": "slept 7h avg", "nutrition": "2000 kcal today"},
            )

    assert "slept 7h avg" in result
    assert "2000 kcal today" in result
    assert "sleep-agent" in result
    assert "nutrition-agent" in result


@pytest.mark.asyncio
async def test_build_workout_prompt_shows_no_logs_fallback():
    with patch("agents.workout.app.prompt.fetch_recent_logs", new_callable=AsyncMock) as mock_logs:
        with patch("agents.workout.app.prompt.search_memories", new_callable=AsyncMock) as mock_mem:
            mock_logs.return_value = []
            mock_mem.return_value = []

            from agents.workout.app.prompt import build_workout_prompt
            result = await build_workout_prompt("log_workout", {})

    assert "No recent workout logs" in result
```

- [ ] **Step 2: Run test to verify failures**

```
pytest tests/test_workout_prompt.py -v
```
Expected: `test_queries_only_workout_logs` FAILS (currently calls DB twice), `test_includes_peer_artifacts` FAILS.

- [ ] **Step 3: Update `agents/workout/app/prompt.py`**

```python
# agents/workout/app/prompt.py
from shared.db import fetch_recent_logs
from shared.vector import search_memories


async def build_workout_prompt(task: str, params: dict, peer_artifacts: dict | None = None) -> str:
    workout_logs = await fetch_recent_logs("workout", limit=10)
    memories = await search_memories("workout_memories", task, limit=5)

    workout_text = "\n".join(
        f"- {r['recorded_at'].date()} | {r['type']} | {r['data']}"
        for r in workout_logs
    ) or "No recent workout logs."

    memories_text = "\n".join(
        f"- {m.get('text', '')}" for m in memories
    ) or "No relevant memories."

    peer = peer_artifacts or {}
    sleep_section = (
        f"\n## Sleep context (from sleep-agent):\n{peer['sleep']}"
        if peer.get("sleep") else ""
    )
    nutrition_section = (
        f"\n## Nutrition context (from nutrition-agent):\n{peer['nutrition']}"
        if peer.get("nutrition") else ""
    )

    return f"""You are a personal workout and training assistant. You have access to the user's training history and context from peer agents.

## Recent workouts (last 10):
{workout_text}
{sleep_section}{nutrition_section}

## Relevant memories:
{memories_text}

## User request:
Task: {task}
Params: {params}

Respond in the user's language. Be concise, specific, and actionable. Reference actual data when relevant.
Workout types tracked: strength (exercises/sets/reps/weight_kg), cycling (distance_km/duration_min/avg_hr), combat (discipline: boxing|mma|muay_thai, duration_min, intensity).
For log_workout: confirm what was logged and note any recovery considerations.
For analyze_workout: identify trends in volume, intensity, and recovery across workout types.
For get_recommendations: suggest next session type and intensity based on recent training load and nutrition intake.
If peer context sections are present, synthesize a grouped response covering Workout, Sleep, Nutrition, and Recommendations."""
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_workout_prompt.py -v
```
Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add agents/workout/app/prompt.py tests/test_workout_prompt.py
git commit -m "feat: workout prompt accepts peer_artifacts, removes passive nutrition DB fetch"
```

---

## Task 6: Workout Agent A2A Contract + Peer Calls

**Files:**
- Modify: `agents/workout/app/tasks.py`
- Modify: `tests/test_workout_tasks.py`

- [ ] **Step 1: Update `tests/test_workout_tasks.py`**

```python
# tests/test_workout_tasks.py
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_handle_log_workout_returns_completed():
    with patch("agents.workout.app.tasks.build_workout_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.workout.app.tasks.run_claude") as mock_claude:
            with patch("agents.workout.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.workout.app.tasks.upsert_memory", new_callable=AsyncMock):
                    with patch("agents.workout.app.tasks.fetch_peer_artifacts", new_callable=AsyncMock) as mock_peers:
                        mock_prompt.return_value = "mocked prompt"
                        mock_claude.return_value = "Workout logged: strength session, 60 min."
                        mock_peers.return_value = {}

                        from agents.workout.app.tasks import handle_task
                        result = await handle_task("log_workout", {"type": "strength", "duration_min": 60})

    assert result.status.state == "completed"
    assert "Workout logged" in result.artifacts[0].parts[0].text


@pytest.mark.asyncio
async def test_handle_analyze_workout_returns_completed():
    with patch("agents.workout.app.tasks.build_workout_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.workout.app.tasks.run_claude") as mock_claude:
            with patch("agents.workout.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.workout.app.tasks.upsert_memory", new_callable=AsyncMock):
                    with patch("agents.workout.app.tasks.fetch_peer_artifacts", new_callable=AsyncMock) as mock_peers:
                        mock_prompt.return_value = "mocked prompt"
                        mock_claude.return_value = "Your training volume increased 15% this week."
                        mock_peers.return_value = {}

                        from agents.workout.app.tasks import handle_task
                        result = await handle_task("analyze_workout", {})

    assert result.status.state == "completed"
    assert "training" in result.artifacts[0].parts[0].text.lower()


@pytest.mark.asyncio
async def test_handle_get_workout_recommendations_returns_completed():
    with patch("agents.workout.app.tasks.build_workout_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.workout.app.tasks.run_claude") as mock_claude:
            with patch("agents.workout.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.workout.app.tasks.upsert_memory", new_callable=AsyncMock):
                    with patch("agents.workout.app.tasks.fetch_peer_artifacts", new_callable=AsyncMock) as mock_peers:
                        mock_prompt.return_value = "mocked prompt"
                        mock_claude.return_value = "Rest day recommended based on recent load."
                        mock_peers.return_value = {}

                        from agents.workout.app.tasks import handle_task
                        result = await handle_task("get_recommendations", {})

    assert result.status.state == "completed"
    assert result.artifacts[0].parts[0].text == "Rest day recommended based on recent load."


@pytest.mark.asyncio
async def test_handle_unknown_workout_task_returns_failed():
    from agents.workout.app.tasks import handle_task
    result = await handle_task("fly_to_moon", {})
    assert result.status.state == "failed"
    assert "Unknown task" in result.artifacts[0].parts[0].text


@pytest.mark.asyncio
async def test_peer_artifacts_injected_into_prompt():
    """Pre-fetched peer_artifacts kwarg bypasses fetch_peer_artifacts and flows to prompt."""
    with patch("agents.workout.app.tasks.build_workout_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.workout.app.tasks.run_claude") as mock_claude:
            with patch("agents.workout.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.workout.app.tasks.upsert_memory", new_callable=AsyncMock):
                    with patch("agents.workout.app.tasks.fetch_peer_artifacts", new_callable=AsyncMock) as mock_peers:
                        mock_prompt.return_value = "mocked prompt"
                        mock_claude.return_value = "Grouped analysis."
                        pre_fetched = {"sleep": "slept 7h", "nutrition": "2000 kcal"}

                        from agents.workout.app.tasks import handle_task
                        await handle_task("analyze_workout", {}, peer_artifacts=pre_fetched)

    mock_peers.assert_not_called()
    assert mock_prompt.call_args.args[2] == pre_fetched
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_workout_tasks.py -v
```
Expected: all FAILED — old return format and missing `fetch_peer_artifacts`.

- [ ] **Step 3: Update `agents/workout/app/tasks.py`**

```python
# agents/workout/app/tasks.py
import asyncio
import json
import logging
import uuid

import httpx

from shared.a2a import A2ATask, Artifact, TaskStatus, TextPart
from shared.claude_runner import run_claude
from shared.db import insert_task
from shared.vector import upsert_memory
from .prompt import build_workout_prompt

logger = logging.getLogger(__name__)

SUPPORTED_TASKS = {"log_workout", "analyze_workout", "get_recommendations"}

_PEER_TASK_NAMES = {
    "sleep": "analyze_sleep",
    "nutrition": "analyze_nutrition",
}


async def _call_peer(url: str, task_name: str) -> str:
    """POST to a peer agent's /tasks endpoint, return artifact text."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{url}/tasks",
                json={"task": task_name, "params": {"context": "summary requested by workout-agent"}},
            )
            resp.raise_for_status()
            data = resp.json()
            artifacts = data.get("artifacts", [])
            if artifacts and artifacts[0].get("parts"):
                return artifacts[0]["parts"][0].get("text", "(данные недоступны)")
    except Exception as e:
        logger.warning("Peer call to %s failed: %s", url, e)
    return "(данные недоступны)"


async def fetch_peer_artifacts(peer_agents: dict) -> dict[str, str]:
    """Call all known peer agents in parallel, return {name: text}."""
    coros = {
        name: _call_peer(info["url"], _PEER_TASK_NAMES[name])
        for name, info in peer_agents.items()
        if name in _PEER_TASK_NAMES and info.get("url")
    }
    if not coros:
        return {}
    texts = await asyncio.gather(*coros.values())
    return dict(zip(coros.keys(), texts))


async def handle_task(
    task: str,
    params: dict,
    peer_artifacts: dict | None = None,
) -> A2ATask:
    task_id = str(uuid.uuid4())

    if task not in SUPPORTED_TASKS:
        return A2ATask(
            id=task_id,
            status=TaskStatus.now("failed"),
            artifacts=[Artifact(name="error", parts=[TextPart(text=f"Unknown task: {task}")])],
        )

    try:
        if peer_artifacts is None:
            peer_artifacts = await fetch_peer_artifacts(params.get("peer_agents", {}))

        prompt = await build_workout_prompt(task, params, peer_artifacts)
        output = await asyncio.to_thread(run_claude, prompt)
        await insert_task("workout", task, params, output)
        await upsert_memory(
            collection="workout_memories",
            id_=str(uuid.uuid4()),
            text=output,
            metadata={"task": task, "params": json.dumps(params)},
        )

        result = A2ATask(
            id=task_id,
            status=TaskStatus.now("completed"),
            artifacts=[Artifact(name="analysis", parts=[TextPart(text=output)])],
        )

        webhook_url = params.get("webhook_url")
        if webhook_url:
            asyncio.create_task(_send_webhook(webhook_url, result.model_dump()))

        return result
    except Exception as e:
        return A2ATask(
            id=task_id,
            status=TaskStatus.now("failed"),
            artifacts=[Artifact(name="error", parts=[TextPart(text=str(e))])],
        )


async def _send_webhook(url: str, payload: dict) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=payload)
    except Exception as e:
        logger.warning("Webhook delivery failed to %s: %s", url, e)
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_workout_tasks.py -v
```
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add agents/workout/app/tasks.py tests/test_workout_tasks.py
git commit -m "feat: workout agent A2A contract with parallel peer calls and webhook support"
```

---

## Task 7: Workout Agent `/tasks/stream` with Peer Streaming

**Files:**
- Modify: `agents/workout/app/main.py`

- [ ] **Step 1: Update `agents/workout/app/main.py`**

```python
# agents/workout/app/main.py
import json
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from shared.a2a import A2ATaskRequest
from .agent_card import AGENT_CARD
from .tasks import handle_task, fetch_peer_artifacts

app = FastAPI(title="Workout Agent")


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@app.get("/.well-known/agent.json")
async def agent_card():
    return AGENT_CARD


@app.post("/tasks")
async def create_task(req: A2ATaskRequest):
    return await handle_task(req.task, req.params)


@app.post("/tasks/stream")
async def stream_task(req: A2ATaskRequest):
    task_id = req.id or str(uuid.uuid4())
    peer_agents = req.params.get("peer_agents", {})

    async def generate():
        ts = lambda: datetime.now(timezone.utc).isoformat()
        yield _sse({"id": task_id, "status": {"state": "submitted", "timestamp": ts()}})
        yield _sse({"id": task_id, "status": {"state": "working", "timestamp": ts()}})

        # Fetch peer artifacts and stream each one as it arrives
        peer_artifacts = await fetch_peer_artifacts(peer_agents)
        for name, text in peer_artifacts.items():
            yield _sse({
                "id": task_id,
                "status": {"state": "working", "timestamp": ts()},
                "artifacts": [{"name": f"peer_{name}", "parts": [{"type": "text", "text": text}]}],
            })

        # Pass pre-fetched artifacts to avoid double peer calls
        result = await handle_task(req.task, req.params, peer_artifacts=peer_artifacts)
        yield _sse(result.model_dump())

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 2: Smoke-test the endpoint manually (optional if Docker is running)**

```
curl -N -X POST http://localhost:8002/tasks/stream \
  -H "Content-Type: application/json" \
  -d '{"task": "analyze_workout", "params": {}}'
```
Expected: SSE lines with `submitted`, `working`, `completed` states.

- [ ] **Step 3: Commit**

```bash
git add agents/workout/app/main.py
git commit -m "feat: workout /tasks/stream with peer artifact streaming events"
```

---

## Task 8: Orchestrator — Peer Injection + AG-UI Stream Proxy with Agent State Display

**Files:**
- Modify: `orchestrator/app/main.py`
- Modify: `tests/test_orchestrator_stream.py`

- [ ] **Step 1: Update `tests/test_orchestrator_stream.py`**

The test must now mock `httpx.AsyncClient` to return A2A-format SSE from `/tasks/stream`:

```python
# tests/test_orchestrator_stream.py
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport


def parse_sse(raw: str) -> list[dict]:
    events = []
    for line in raw.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


def _make_stream_mock(sse_lines: list[str]):
    """Build a mock for httpx streaming context manager."""
    mock_resp = MagicMock()
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)

    async def aiter_lines():
        for line in sse_lines:
            yield line

    mock_resp.aiter_lines = aiter_lines

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(return_value=mock_resp)
    return mock_client


@pytest.mark.asyncio
async def test_chat_stream_emits_agui_events():
    """POST /chat/stream emits RunStarted → TextMessageContent → RunFinished."""
    task_id = "test-task-id"
    sse_lines = [
        f'data: {json.dumps({"id": task_id, "status": {"state": "submitted", "timestamp": "2026-04-13T00:00:00Z"}})}',
        f'data: {json.dumps({"id": task_id, "status": {"state": "working", "timestamp": "2026-04-13T00:00:01Z"}})}',
        f'data: {json.dumps({"id": task_id, "status": {"state": "completed", "timestamp": "2026-04-13T00:00:02Z"}, "artifacts": [{"name": "analysis", "parts": [{"type": "text", "text": "Sleep better tonight."}]}]})}',
    ]
    mock_client = _make_stream_mock(sse_lines)

    with patch("orchestrator.app.main.get_agent_url", return_value="http://agent-sleep:8001"):
        with patch("orchestrator.app.main.classify_intent", return_value="sleep"):
            with patch("orchestrator.app.main._build_peer_agents", return_value={}):
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
    assert "TextMessageContent" in types
    full_text = "".join(e["delta"] for e in events if e.get("type") == "TextMessageContent")
    assert "Sleep better tonight." in full_text


@pytest.mark.asyncio
async def test_chat_stream_emits_peer_status_for_workout():
    """Workout stream emits peer status messages before the final answer."""
    task_id = "wk-task"
    sse_lines = [
        f'data: {json.dumps({"id": task_id, "status": {"state": "submitted", "timestamp": ""}})}',
        f'data: {json.dumps({"id": task_id, "status": {"state": "working", "timestamp": ""}})}',
        f'data: {json.dumps({"id": task_id, "status": {"state": "working", "timestamp": ""}, "artifacts": [{"name": "peer_sleep", "parts": [{"type": "text", "text": "slept 7h"}]}]})}',
        f'data: {json.dumps({"id": task_id, "status": {"state": "working", "timestamp": ""}, "artifacts": [{"name": "peer_nutrition", "parts": [{"type": "text", "text": "2000 kcal"}]}]})}',
        f'data: {json.dumps({"id": task_id, "status": {"state": "completed", "timestamp": ""}, "artifacts": [{"name": "analysis", "parts": [{"type": "text", "text": "Grouped analysis."}]}]})}',
    ]
    mock_client = _make_stream_mock(sse_lines)

    with patch("orchestrator.app.main.get_agent_url", return_value="http://agent-workout:8002"):
        with patch("orchestrator.app.main.classify_intent", return_value="workout"):
            with patch("orchestrator.app.main._build_peer_agents", return_value={}):
                with patch("httpx.AsyncClient", return_value=mock_client):
                    from orchestrator.app.main import app
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                        resp = await client.post("/chat/stream", json={
                            "messages": [{"role": "user", "content": "How was my workout?"}],
                        })

    events = parse_sse(resp.text)
    full_text = "".join(e.get("delta", "") for e in events if e.get("type") == "TextMessageContent")
    assert "sleep-agent" in full_text
    assert "nutrition-agent" in full_text
    assert "Grouped analysis." in full_text


@pytest.mark.asyncio
async def test_chat_stream_no_user_message_returns_400():
    from orchestrator.app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/chat/stream", json={"messages": []})
    assert resp.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_orchestrator_stream.py -v
```
Expected: `test_chat_stream_emits_agui_events` FAILED — orchestrator still calls `/tasks` not `/tasks/stream`, and `_build_peer_agents` doesn't exist.

- [ ] **Step 3: Update `orchestrator/app/main.py`**

Replace the entire file:

```python
# orchestrator/app/main.py
import json
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .db import clear_activity, get_stats, get_tasks_today
from .registry import check_agent_health, discover_agents, get_agent_url, get_registry, list_agents
from .router import classify_intent

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


def _build_peer_agents(primary: str) -> dict:
    """Return all registry agents except primary, formatted for A2A peer_agents param."""
    registry = get_registry()
    return {
        name: {"url": entry["url"], "card": entry.get("card", {})}
        for name, entry in registry.items()
        if name != primary
    }


def _artifact_text(data: dict) -> str:
    """Extract text from first A2A artifact, fall back to legacy 'output' field."""
    artifacts = data.get("artifacts", [])
    if artifacts and artifacts[0].get("parts"):
        return artifacts[0]["parts"][0].get("text", "")
    return data.get("output", "")


@app.post("/chat")
async def chat(req: ChatRequest):
    agent_name = classify_intent(req.message)

    if agent_name == "sync":
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post("http://sync-service:8080/sync")
                resp.raise_for_status()
                data = resp.json()
                text = f"Sync complete: {data['synced']} records synced, {data['skipped']} skipped."
                if data.get("errors"):
                    text += f" Errors: {'; '.join(data['errors'][:3])}"
            return {"output": text}
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Sync service error: {str(e)}")

    agent_url = get_agent_url(agent_name)
    if not agent_url:
        raise HTTPException(
            status_code=503,
            detail=f"Agent '{agent_name}' is not available. Available: {list_agents()}",
        )

    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            resp = await client.post(
                f"{agent_url}/tasks",
                json={
                    "id": str(uuid.uuid4()),
                    "task": AGENT_DEFAULT_TASK.get(agent_name, f"analyze_{agent_name}"),
                    "params": {"message": req.message, "peer_agents": _build_peer_agents(agent_name)},
                },
            )
            resp.raise_for_status()
            return {"output": _artifact_text(resp.json())}
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
    thread_id = req.threadId or str(uuid.uuid4())
    run_id = req.runId or str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    user_messages = [m for m in req.messages if m.get("role") == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")

    message = user_messages[-1].get("content", "")
    agent_name = classify_intent(message)

    if agent_name == "sync":
        async def sync_stream():
            yield _sse({"type": "RunStarted", "threadId": thread_id, "runId": run_id})
            yield _sse({"type": "TextMessageStart", "messageId": message_id, "role": "assistant"})
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post("http://sync-service:8080/sync")
                    resp.raise_for_status()
                    data = resp.json()
                    text = f"Sync complete: {data['synced']} records synced, {data['skipped']} skipped."
                    if data.get("errors"):
                        text += f" Errors: {'; '.join(data['errors'][:3])}"
            except Exception as e:
                text = f"Sync failed: {str(e)}"
            yield _sse({"type": "TextMessageContent", "messageId": message_id, "delta": text})
            yield _sse({"type": "TextMessageEnd", "messageId": message_id})
            yield _sse({"type": "RunFinished", "threadId": thread_id, "runId": run_id})

        return StreamingResponse(
            sync_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    agent_url = get_agent_url(agent_name)

    # Peer name label for status messages shown in chat
    _PEER_LABELS = {"sleep": "sleep-agent", "nutrition": "nutrition-agent", "workout": "workout-agent"}

    async def event_stream():
        yield _sse({"type": "RunStarted", "threadId": thread_id, "runId": run_id})
        yield _sse({"type": "TextMessageStart", "messageId": message_id, "role": "assistant"})

        if not agent_url:
            yield _sse({"type": "TextMessageContent", "messageId": message_id,
                        "delta": f"Agent '{agent_name}' is not available."})
            yield _sse({"type": "TextMessageEnd", "messageId": message_id})
            yield _sse({"type": "RunFinished", "threadId": thread_id, "runId": run_id})
            return

        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                async with client.stream(
                    "POST",
                    f"{agent_url}/tasks/stream",
                    json={
                        "id": str(uuid.uuid4()),
                        "task": AGENT_DEFAULT_TASK.get(agent_name, f"analyze_{agent_name}"),
                        "params": {"message": message, "peer_agents": _build_peer_agents(agent_name)},
                    },
                ) as resp:
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        event = json.loads(line[6:])
                        state = event.get("status", {}).get("state")
                        artifacts = event.get("artifacts", [])

                        for artifact in artifacts:
                            name = artifact.get("name", "")
                            parts = artifact.get("parts", [])
                            text = parts[0].get("text", "") if parts else ""
                            if not text:
                                continue

                            # Peer artifacts: show agent name header + content
                            if name.startswith("peer_"):
                                peer_key = name[5:]  # "sleep" or "nutrition"
                                label = _PEER_LABELS.get(peer_key, peer_key)
                                delta = f"\n\n*Консультирую {label}...*\n\n{text}"
                                yield _sse({"type": "TextMessageContent", "messageId": message_id, "delta": delta})
                            elif state == "completed":
                                yield _sse({"type": "TextMessageContent", "messageId": message_id, "delta": text})

        except Exception as e:
            yield _sse({"type": "TextMessageContent", "messageId": message_id,
                        "delta": f"Error contacting agent: {str(e)}"})

        yield _sse({"type": "TextMessageEnd", "messageId": message_id})
        yield _sse({"type": "RunFinished", "threadId": thread_id, "runId": run_id})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/stats")
async def stats():
    return await get_stats()


@app.delete("/activity")
async def delete_activity():
    deleted = await clear_activity()
    return {"deleted": deleted}


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

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_orchestrator_stream.py -v
```
Expected: 3 PASSED.

- [ ] **Step 5: Run full test suite to verify no regressions**

```
pytest tests/ -v --tb=short 2>&1 | tail -30
```
Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/app/main.py tests/test_orchestrator_stream.py
git commit -m "feat: orchestrator injects peer_agents and proxies A2A stream with agent state display"
```

---

## Final Verification

- [ ] **Run full test suite**

```
pytest tests/ -v 2>&1 | tail -40
```
Expected: all tests PASSED, no failures.

- [ ] **If Docker is running, smoke-test end-to-end**

```bash
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Как мои тренировки на этой неделе?"}]}'
```
Expected SSE output:
```
data: {"type": "RunStarted", ...}
data: {"type": "TextMessageStart", ...}
data: {"type": "TextMessageContent", ..., "delta": "\n\n*Консультирую sleep-agent...*\n\n..."}
data: {"type": "TextMessageContent", ..., "delta": "\n\n*Консультирую nutrition-agent...*\n\n..."}
data: {"type": "TextMessageContent", ..., "delta": "...grouped analysis..."}
data: {"type": "TextMessageEnd", ...}
data: {"type": "RunFinished", ...}
```
