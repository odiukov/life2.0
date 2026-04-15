# Agent State Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream live agent process state (`currentStep`, `activeAgent`, `toolCalls`, `lastLoggedEntry`) from the orchestrator LangGraph agent to the chat UI via CopilotKit CoAgents + AG-UI `StateSnapshot`/`StateDelta`, removing the generic "spinner" UX during A2A calls.

**Architecture:** Extend the orchestrator's LangGraph state schema with a `TypedDict`, refactor A2A tools to call `copilotkit_emit_state` mid-execution and return `Command(update=…)` on finish, add a second named `log_entry` artifact to sub-agent executors for structured logging confirmation, then subscribe via `useCoAgent<HealthAgentState>({name:"default"})` on the frontend and render two small components (`AgentStatusBar`, `LastLoggedCard`) inside `DashboardPage`.

**Tech Stack:** Python 3.12 (orchestrator, sub-agents) — LangGraph ≥0.2.50 (`create_react_agent` with `state_schema`), `copilotkit==0.1.39` (Python SDK), `a2a-sdk==0.3.26` (`Artifact` + `DataPart`), FastAPI; TypeScript/React (frontend) — CopilotKit React (`@copilotkit/react-core` `useCoAgent`), Vitest + MSW for integration tests.

**Spec:** `docs/superpowers/specs/2026-04-15-agent-state-snapshot-design.md`

---

## File map

**New:**
- `orchestrator/app/state.py` — `HealthAgentState`, `ToolCall`, `LogEntry` TypedDicts.
- `agui-frontend/src/components/AgentStatusBar.tsx` + `.test.tsx`.
- `agui-frontend/src/components/LastLoggedCard.tsx` + `.test.tsx`.
- `tests/orchestrator/test_artifact_extraction.py`.
- `tests/orchestrator/test_health_agent_state.py`.
- `tests/agents/test_sleep_executor_log_artifact.py`.
- `tests/agents/test_workout_executor_log_artifact.py`.
- `tests/agents/test_nutrition_executor_log_artifact.py`.

**Modified:**
- `orchestrator/requirements.txt` — add `copilotkit>=0.1.39`.
- `orchestrator/app/health_agent.py` — tools refactored with `emit_state`+`Command`; `_call_agent` → `_call_agent_with_artifact`; `create_react_agent(state_schema=HealthAgentState)`.
- `agents/{sleep,workout,nutrition}/app/executor.py` — emit second `log_entry` artifact for `log_*` skills.
- `agui-frontend/src/types.ts` — add `ToolCall`, `LogEntry`, `HealthAgentState`.
- `agui-frontend/src/pages/DashboardPage.tsx` — wire `useCoAgent`, mount new components.

---

## Task 1: Sub-agent — emit `log_entry` artifact (TDD)

Extend each sub-agent executor to emit a second named `log_entry` artifact after successful `log_*` skills. This gives the orchestrator a structured confirmation without parsing free-text.

**Files:**
- Modify: `agents/sleep/app/executor.py`
- Modify: `agents/workout/app/executor.py`
- Modify: `agents/nutrition/app/executor.py`
- Test: `tests/agents/test_sleep_executor_log_artifact.py`
- Test: `tests/agents/test_workout_executor_log_artifact.py`
- Test: `tests/agents/test_nutrition_executor_log_artifact.py`

The three executors are structurally identical (only differ in agent name, skills set, peer keywords). We do sleep first, then replicate.

### Task 1a: Write failing test for sleep `log_entry` artifact

- [ ] **Step 1: Create test file**

Create `tests/agents/test_sleep_executor_log_artifact.py`:

```python
"""sleep executor emits a log_entry artifact only for log_sleep skill."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from a2a.types import Artifact, DataPart, Message, Part, Role, TextPart


class _FakeEventQueue:
    def __init__(self) -> None:
        self.events: list = []

    async def enqueue_event(self, evt):  # noqa: D401
        self.events.append(evt)


def _ctx(message_text: str, skill_id: str):
    from a2a.server.agent_execution import RequestContext
    msg = Message(
        role=Role.user,
        parts=[Part(root=TextPart(text=message_text))],
        message_id="m1",
        metadata={"skillId": skill_id},
    )
    return RequestContext(message=msg, task_id="t1", context_id="c1")


def _collected_artifacts(queue: _FakeEventQueue) -> list[Artifact]:
    out = []
    for e in queue.events:
        art = getattr(e, "artifact", None)
        if art is not None:
            out.append(art)
    return out


@pytest.mark.asyncio
@patch("agents.sleep.app.executor.insert_task_record", new=AsyncMock())
@patch("agents.sleep.app.executor.upsert_memory", new=AsyncMock())
@patch("agents.sleep.app.executor.fetch_peer_artifacts", new=AsyncMock(return_value={}))
@patch("agents.sleep.app.executor.run_claude", return_value="ok logged")
async def test_log_sleep_emits_log_entry_artifact(run_claude_mock):
    from agents.sleep.app.executor import SleepAgentExecutor

    queue = _FakeEventQueue()
    await SleepAgentExecutor().execute(_ctx("slept 8h yesterday", "log_sleep"), queue)
    arts = _collected_artifacts(queue)
    names = [a.name for a in arts]
    assert "log_entry" in names
    log_art = next(a for a in arts if a.name == "log_entry")
    data_part = log_art.parts[0].root
    assert isinstance(data_part, DataPart)
    assert data_part.data["summary"].startswith("slept 8h")
    assert "timestamp" in data_part.data


@pytest.mark.asyncio
@patch("agents.sleep.app.executor.insert_task_record", new=AsyncMock())
@patch("agents.sleep.app.executor.upsert_memory", new=AsyncMock())
@patch("agents.sleep.app.executor.fetch_peer_artifacts", new=AsyncMock(return_value={}))
@patch("agents.sleep.app.executor.run_claude", return_value="analysis text")
async def test_analyze_sleep_does_not_emit_log_entry(run_claude_mock):
    from agents.sleep.app.executor import SleepAgentExecutor

    queue = _FakeEventQueue()
    await SleepAgentExecutor().execute(_ctx("how did I sleep this week?", "analyze_sleep"), queue)
    arts = _collected_artifacts(queue)
    names = [a.name for a in arts]
    assert "log_entry" not in names
    assert "analysis" in names
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/agents/test_sleep_executor_log_artifact.py -v
```

Expected: FAIL — `log_entry` artifact not present (current executor emits only `analysis`).

### Task 1b: Implement — emit `log_entry` artifact in sleep executor

- [ ] **Step 3: Add DataPart import and helper in `agents/sleep/app/executor.py`**

At the top of the file, extend the `a2a.types` import:

```python
from a2a.types import (
    Artifact,
    DataPart,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
```

Add these imports near the top:

```python
from datetime import datetime, timezone
```

Add a helper function above the existing `_emit_artifact`:

```python
async def _emit_log_entry_artifact(
    event_queue: EventQueue,
    task_id: str,
    context_id: str,
    summary: str,
) -> None:
    artifact = Artifact(
        artifact_id=str(uuid.uuid4()),
        name="log_entry",
        parts=[Part(root=DataPart(data={
            "summary": summary[:120],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }))],
    )
    evt = TaskArtifactUpdateEvent(
        task_id=task_id,
        context_id=context_id,
        artifact=artifact,
        append=True,
        last_chunk=False,
    )
    await event_queue.enqueue_event(evt)
```

- [ ] **Step 4: Call helper after successful `log_*` skill**

Find the block inside `SleepAgentExecutor.execute` right before the final `_emit_artifact(... "analysis" ...)`:

```python
await _emit_artifact(event_queue, task_id, context_id, "analysis", output)
await _emit_status(event_queue, task_id, context_id, TaskState.completed, final=True)
```

Replace with:

```python
if skill_id.startswith("log_"):
    await _emit_log_entry_artifact(event_queue, task_id, context_id, message)
await _emit_artifact(event_queue, task_id, context_id, "analysis", output)
await _emit_status(event_queue, task_id, context_id, TaskState.completed, final=True)
```

- [ ] **Step 5: Run test to verify it passes**

```bash
.venv/bin/pytest tests/agents/test_sleep_executor_log_artifact.py -v
```

Expected: PASS (both tests).

- [ ] **Step 6: Commit**

```bash
git add agents/sleep/app/executor.py tests/agents/test_sleep_executor_log_artifact.py
git commit -m "$(cat <<'EOF'
feat(sleep): emit structured log_entry artifact for log_sleep skill

Downstream orchestrator will read this as state.lastLoggedEntry for
the chat UI — avoids parsing free-text Claude output.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task 1c: Replicate for workout and nutrition

- [ ] **Step 7: Copy test files with agent substitution**

Create `tests/agents/test_workout_executor_log_artifact.py` — identical to the sleep test but:
- Replace `agents.sleep.app.executor` with `agents.workout.app.executor`.
- Replace `SleepAgentExecutor` with `WorkoutAgentExecutor`.
- First test: message `"30 min run today"`, skill `"log_workout"`, assert summary starts with `"30 min run"`.
- Second test: message `"how hard was last week?"`, skill `"analyze_workout"`.

Create `tests/agents/test_nutrition_executor_log_artifact.py` — identical pattern:
- Module `agents.nutrition.app.executor`, class `NutritionAgentExecutor`.
- First test: message `"greek salad 320 kcal"`, skill `"log_meal"`, assert summary starts with `"greek salad"`.
- Second test: message `"analyze my diet"`, skill `"analyze_nutrition"`.

- [ ] **Step 8: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/agents/test_workout_executor_log_artifact.py tests/agents/test_nutrition_executor_log_artifact.py -v
```

Expected: 4 FAILs.

- [ ] **Step 9: Apply the same edit to both executors**

For `agents/workout/app/executor.py` and `agents/nutrition/app/executor.py`:
1. Add `DataPart` to the `a2a.types` import block.
2. Add `from datetime import datetime, timezone`.
3. Add the `_emit_log_entry_artifact` helper (same code as in step 3, paste verbatim).
4. Before `await _emit_artifact(event_queue, task_id, context_id, "analysis", output)`, add the 2-line `if skill_id.startswith("log_"):` guard (same code as step 4).

- [ ] **Step 10: Run all three executor tests**

```bash
.venv/bin/pytest tests/agents/ -v
```

Expected: all 6 tests PASS.

- [ ] **Step 11: Commit**

```bash
git add agents/workout/app/executor.py agents/nutrition/app/executor.py \
  tests/agents/test_workout_executor_log_artifact.py \
  tests/agents/test_nutrition_executor_log_artifact.py
git commit -m "$(cat <<'EOF'
feat(workout,nutrition): emit log_entry artifact for log_* skills

Mirrors the sleep agent change: structured DataPart alongside the
analysis text artifact for downstream state.lastLoggedEntry.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Orchestrator — HealthAgentState TypedDict

Centralize the new state schema in one file so tools and tests share it.

**Files:**
- Create: `orchestrator/app/state.py`

- [ ] **Step 1: Create `orchestrator/app/state.py`**

```python
"""Shared state schema for the orchestrator LangGraph agent.

Consumed by frontend via CopilotKit useCoAgent<HealthAgentState>({name:"default"}).
Keys are camelCase to match JS conventions.
"""
from __future__ import annotations

from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

ToolStatus = Literal["running", "done", "error"]


class ToolCall(TypedDict):
    id: str
    name: str
    skill: NotRequired[str]
    status: ToolStatus
    startedAt: str  # ISO8601
    endedAt: NotRequired[str]
    error: NotRequired[str]


class LogEntry(TypedDict):
    agent: Literal["sleep", "workout", "nutrition"]
    skill: str
    summary: str
    timestamp: str


class HealthAgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    currentStep: NotRequired[str]
    activeAgent: NotRequired[str | None]
    toolCalls: NotRequired[list[ToolCall]]
    lastLoggedEntry: NotRequired[LogEntry | None]
```

- [ ] **Step 2: Smoke-import the module**

```bash
.venv/bin/python -c "from orchestrator.app.state import HealthAgentState, ToolCall, LogEntry; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add orchestrator/app/state.py
git commit -m "$(cat <<'EOF'
feat(orchestrator): add HealthAgentState TypedDict for CoAgent streaming

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Orchestrator — artifact extraction helper (TDD)

Replace `_call_agent` with `_call_agent_with_artifact` that also pulls the `log_entry` DataPart.

**Files:**
- Modify: `orchestrator/app/health_agent.py` (add helper; keep old `_call_agent` wrapper for now — removed in Task 4).
- Test: `tests/orchestrator/test_artifact_extraction.py`

- [ ] **Step 1: Write failing test**

Create `tests/orchestrator/test_artifact_extraction.py`:

```python
"""_call_agent_with_artifact extracts text + log_entry from A2A Task artifacts."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from a2a.types import Artifact, DataPart, Message, Part, Role, Task, TaskState, TaskStatus, TextPart


def _task_with(text: str, log_entry: dict | None) -> Task:
    arts = [
        Artifact(
            artifact_id=str(uuid4()),
            name="analysis",
            parts=[Part(root=TextPart(text=text))],
        )
    ]
    if log_entry is not None:
        arts.append(
            Artifact(
                artifact_id=str(uuid4()),
                name="log_entry",
                parts=[Part(root=DataPart(data=log_entry))],
            )
        )
    return Task(
        id="t1",
        context_id="c1",
        status=TaskStatus(state=TaskState.completed),
        artifacts=arts,
        history=[],
    )


class _FakeClient:
    def __init__(self, task: Task):
        self._task = task

    async def send_message(self, msg: Message):
        yield (self._task, None)


@pytest.mark.asyncio
@patch("orchestrator.app.health_agent._resolve_url", return_value="http://fake")
@patch("orchestrator.app.health_agent.get_client")
async def test_extracts_text_and_log_entry(get_client_mock, _url_mock):
    task = _task_with(
        "Logged: 30 min run",
        {"summary": "30 min run", "timestamp": "2026-04-15T10:00:00+00:00"},
    )
    get_client_mock.return_value = _FakeClient(task)
    from orchestrator.app.health_agent import _call_agent_with_artifact

    text, log_entry = await _call_agent_with_artifact("workout", "30 min run", "log_workout")
    assert text == "Logged: 30 min run"
    assert log_entry == {"summary": "30 min run", "timestamp": "2026-04-15T10:00:00+00:00"}


@pytest.mark.asyncio
@patch("orchestrator.app.health_agent._resolve_url", return_value="http://fake")
@patch("orchestrator.app.health_agent.get_client")
async def test_no_log_entry_when_absent(get_client_mock, _url_mock):
    task = _task_with("analysis text", None)
    get_client_mock.return_value = _FakeClient(task)
    from orchestrator.app.health_agent import _call_agent_with_artifact

    text, log_entry = await _call_agent_with_artifact("sleep", "how did I sleep?", "analyze_sleep")
    assert text == "analysis text"
    assert log_entry is None


@pytest.mark.asyncio
@patch("orchestrator.app.health_agent._resolve_url", return_value=None)
async def test_unavailable_agent_returns_error_text(_url_mock):
    from orchestrator.app.health_agent import _call_agent_with_artifact

    text, log_entry = await _call_agent_with_artifact("sleep", "x", "log_sleep")
    assert "unavailable" in text.lower()
    assert log_entry is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/orchestrator/test_artifact_extraction.py -v
```

Expected: FAIL (function undefined).

- [ ] **Step 3: Implement `_call_agent_with_artifact`**

Open `orchestrator/app/health_agent.py`. Replace the existing `_extract_text_from_task` and `_call_agent` functions with:

```python
def _extract_text_from_task(task: Task) -> str:
    for art in task.artifacts or []:
        for p in art.parts or []:
            root = getattr(p, "root", p)
            text = getattr(root, "text", None)
            if text:
                return text
    return ""


def _extract_log_entry_from_task(task: Task) -> dict | None:
    for art in task.artifacts or []:
        if art.name != "log_entry":
            continue
        for p in art.parts or []:
            root = getattr(p, "root", p)
            data = getattr(root, "data", None)
            if isinstance(data, dict) and "summary" in data and "timestamp" in data:
                return data
    return None


async def _call_agent_with_artifact(
    agent: str, message: str, skill: str
) -> tuple[str, dict | None]:
    url = _resolve_url(agent)
    if not url:
        return f"Agent '{agent}' is currently unavailable.", None
    try:
        client = await get_client(url)
        msg = Message(
            role=Role.user,
            parts=[Part(root=TextPart(text=message))],
            message_id=str(uuid.uuid4()),
            metadata={"skillId": skill},
        )
        text = ""
        log_entry: dict | None = None
        async for resp in client.send_message(msg):
            if isinstance(resp, tuple):
                task, _update = resp
                if not text:
                    text = _extract_text_from_task(task)
                if log_entry is None:
                    log_entry = _extract_log_entry_from_task(task)
            elif isinstance(resp, Message):
                if not text:
                    text = _extract_text_from_message(resp)
        if not text:
            text = f"Agent '{agent}' returned no content."
        return text, log_entry
    except Exception as e:
        return f"Error calling {agent} agent: {e}", None
```

Keep the existing `_call_agent` for compatibility during Task 4 — add this one-liner wrapper right below:

```python
async def _call_agent(agent: str, message: str, skill: str) -> str:
    text, _ = await _call_agent_with_artifact(agent, message, skill)
    return text
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/pytest tests/orchestrator/test_artifact_extraction.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/app/health_agent.py tests/orchestrator/test_artifact_extraction.py
git commit -m "$(cat <<'EOF'
feat(orchestrator): extract log_entry artifact from A2A Task responses

New _call_agent_with_artifact returns (text, log_entry|None). Old
_call_agent kept as wrapper for one more commit.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Orchestrator — add `copilotkit` dep and refactor tools (TDD)

Refactor each A2A tool to: inject `config`/`tool_call_id`/`state`, emit interim state, call `_call_agent_with_artifact`, return `Command(update=…)`. Switch `create_react_agent` to use `HealthAgentState`.

**Files:**
- Modify: `orchestrator/requirements.txt`
- Modify: `orchestrator/app/health_agent.py`
- Test: `tests/orchestrator/test_health_agent_state.py`

### Task 4a: Add dependency

- [ ] **Step 1: Append to `orchestrator/requirements.txt`**

Open `orchestrator/requirements.txt`, add a line (preserve alpha order if any):

```
copilotkit>=0.1.39,<0.2
```

- [ ] **Step 2: Install into venv**

```bash
.venv/bin/pip install 'copilotkit>=0.1.39,<0.2'
```

Expected: installs or reports already satisfied.

- [ ] **Step 3: Verify helper import works**

```bash
.venv/bin/python -c "from copilotkit.langgraph import copilotkit_emit_state; print('ok')"
```

Expected: `ok`.

### Task 4b: Write failing test for tool behavior

- [ ] **Step 4: Create `tests/orchestrator/test_health_agent_state.py`**

```python
"""A2A tools emit intermediate state and return Command(update=...) with
toolCalls transitions + lastLoggedEntry on log_* skills."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import ToolMessage
from langgraph.types import Command


class _FakeRunnableConfig(dict):
    """Minimal RunnableConfig stand-in."""


def _invoke(tool, **kwargs):
    """Call a @tool-decorated function's underlying coroutine directly."""
    return tool.coroutine(**kwargs) if hasattr(tool, "coroutine") else tool.ainvoke(kwargs)


@pytest.mark.asyncio
@patch("orchestrator.app.health_agent.copilotkit_emit_state", new_callable=AsyncMock)
@patch(
    "orchestrator.app.health_agent._call_agent_with_artifact",
    new=AsyncMock(return_value=(
        "Logged: 30 min run",
        {"summary": "30 min run", "timestamp": "2026-04-15T10:00:00+00:00"},
    )),
)
async def test_ask_workout_log_emits_running_then_returns_done_with_log_entry(emit_mock):
    from orchestrator.app.health_agent import ask_workout_agent

    state = {"messages": [], "toolCalls": []}
    cmd = await ask_workout_agent.ainvoke({
        "message": "30 min run",
        "skill": "log_workout",
        "config": _FakeRunnableConfig(),
        "tool_call_id": "tc1",
        "state": state,
    })

    assert emit_mock.await_count == 1
    emitted_state = emit_mock.await_args.args[1]
    assert emitted_state["currentStep"] == "querying workout (log_workout)"
    assert emitted_state["activeAgent"] == "workout"
    assert len(emitted_state["toolCalls"]) == 1
    assert emitted_state["toolCalls"][0]["status"] == "running"
    assert emitted_state["toolCalls"][0]["id"] == "tc1"

    assert isinstance(cmd, Command)
    upd = cmd.update
    assert upd["activeAgent"] is None
    assert upd["currentStep"] == "composing"
    assert upd["toolCalls"][0]["status"] == "done"
    assert upd["lastLoggedEntry"] == {
        "agent": "workout",
        "skill": "log_workout",
        "summary": "30 min run",
        "timestamp": "2026-04-15T10:00:00+00:00",
    }
    assert isinstance(upd["messages"][0], ToolMessage)
    assert upd["messages"][0].tool_call_id == "tc1"


@pytest.mark.asyncio
@patch("orchestrator.app.health_agent.copilotkit_emit_state", new_callable=AsyncMock)
@patch(
    "orchestrator.app.health_agent._call_agent_with_artifact",
    new=AsyncMock(return_value=("analysis text", None)),
)
async def test_ask_sleep_analyze_does_not_set_last_logged_entry(emit_mock):
    from orchestrator.app.health_agent import ask_sleep_agent

    state = {"messages": [], "toolCalls": []}
    cmd = await ask_sleep_agent.ainvoke({
        "message": "how did I sleep?",
        "skill": "analyze_sleep",
        "config": _FakeRunnableConfig(),
        "tool_call_id": "tc2",
        "state": state,
    })
    assert "lastLoggedEntry" not in cmd.update


@pytest.mark.asyncio
@patch("orchestrator.app.health_agent.copilotkit_emit_state", new_callable=AsyncMock)
@patch(
    "orchestrator.app.health_agent._call_agent_with_artifact",
    side_effect=RuntimeError("boom"),
)
async def test_tool_exception_sets_error_status(_call_mock, _emit_mock):
    from orchestrator.app.health_agent import ask_nutrition_agent

    state = {"messages": [], "toolCalls": []}
    cmd = await ask_nutrition_agent.ainvoke({
        "message": "x",
        "skill": "log_meal",
        "config": _FakeRunnableConfig(),
        "tool_call_id": "tc3",
        "state": state,
    })
    assert cmd.update["toolCalls"][0]["status"] == "error"
    assert "boom" in cmd.update["toolCalls"][0]["error"]
    assert "lastLoggedEntry" not in cmd.update
```

- [ ] **Step 5: Run test to verify it fails**

```bash
.venv/bin/pytest tests/orchestrator/test_health_agent_state.py -v
```

Expected: 3 FAILs — tools still return `str`, not `Command`.

### Task 4c: Refactor tools

- [ ] **Step 6: Update imports at top of `orchestrator/app/health_agent.py`**

Replace the existing imports block with:

```python
"""LangGraph ReAct agent — one generic tool per A2A peer with CoAgent state streaming."""
from __future__ import annotations

import uuid
import warnings
from datetime import datetime, timezone
from typing import Annotated, Literal

import httpx
from a2a.types import Message, Part, Role, Task, TextPart
from copilotkit.langgraph import copilotkit_emit_state
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from shared.a2a_clients import get_client

from .llm import build_llm
from .state import HealthAgentState, LogEntry, ToolCall
```

- [ ] **Step 7: Add shared helpers above the tools**

Below the existing `_extract_*` / `_call_agent_with_artifact` block (but above the `@tool` definitions), add:

```python
_MAX_TOOL_CALLS = 20


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _running_tool_call(tool_call_id: str, name: str, skill: str) -> ToolCall:
    return {
        "id": tool_call_id,
        "name": name,
        "skill": skill,
        "status": "running",
        "startedAt": _now_iso(),
    }


def _trim(calls: list[ToolCall]) -> list[ToolCall]:
    return calls[-_MAX_TOOL_CALLS:]


async def _run_peer_tool(
    *,
    agent: Literal["sleep", "workout", "nutrition"],
    message: str,
    skill: str,
    tool_name: str,
    config: RunnableConfig,
    tool_call_id: str,
    state: HealthAgentState,
) -> Command:
    prev_calls = list(state.get("toolCalls") or [])
    running = _running_tool_call(tool_call_id, tool_name, skill)
    await copilotkit_emit_state(config, {
        **state,
        "currentStep": f"querying {agent} ({skill})",
        "activeAgent": agent,
        "toolCalls": _trim([*prev_calls, running]),
    })
    try:
        text, log_entry = await _call_agent_with_artifact(agent, message, skill)
        done_call: ToolCall = {**running, "status": "done", "endedAt": _now_iso()}
        update: dict = {
            "currentStep": "composing",
            "activeAgent": None,
            "toolCalls": _trim([*prev_calls, done_call]),
            "messages": [ToolMessage(content=text, tool_call_id=tool_call_id)],
        }
        if skill.startswith("log_") and log_entry:
            entry: LogEntry = {
                "agent": agent,
                "skill": skill,
                "summary": log_entry["summary"],
                "timestamp": log_entry["timestamp"],
            }
            update["lastLoggedEntry"] = entry
        return Command(update=update)
    except Exception as e:
        err_call: ToolCall = {
            **running, "status": "error", "endedAt": _now_iso(), "error": str(e)
        }
        return Command(update={
            "currentStep": "composing",
            "activeAgent": None,
            "toolCalls": _trim([*prev_calls, err_call]),
            "messages": [ToolMessage(content=f"Error: {e}", tool_call_id=tool_call_id)],
        })
```

- [ ] **Step 8: Replace the three `ask_*_agent` tools**

Replace the existing definitions of `ask_sleep_agent`, `ask_workout_agent`, `ask_nutrition_agent` with:

```python
@tool
async def ask_sleep_agent(
    message: str,
    skill: Literal["log_sleep", "analyze_sleep", "get_sleep_recommendations"],
    config: RunnableConfig,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[HealthAgentState, InjectedState],
) -> Command:
    """Call sleep-agent. Use 'log_sleep' to record a new entry, 'analyze_sleep' to
    discuss quality/trends, 'get_sleep_recommendations' for actionable advice."""
    return await _run_peer_tool(
        agent="sleep", message=message, skill=skill, tool_name="ask_sleep_agent",
        config=config, tool_call_id=tool_call_id, state=state,
    )


@tool
async def ask_workout_agent(
    message: str,
    skill: Literal["log_workout", "analyze_workout", "get_workout_recommendations"],
    config: RunnableConfig,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[HealthAgentState, InjectedState],
) -> Command:
    """Call workout-agent. Skills: log_workout / analyze_workout / get_workout_recommendations."""
    return await _run_peer_tool(
        agent="workout", message=message, skill=skill, tool_name="ask_workout_agent",
        config=config, tool_call_id=tool_call_id, state=state,
    )


@tool
async def ask_nutrition_agent(
    message: str,
    skill: Literal["log_meal", "analyze_nutrition", "get_nutrition_recommendations"],
    config: RunnableConfig,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[HealthAgentState, InjectedState],
) -> Command:
    """Call nutrition-agent. Skills: log_meal / analyze_nutrition / get_nutrition_recommendations."""
    return await _run_peer_tool(
        agent="nutrition", message=message, skill=skill, tool_name="ask_nutrition_agent",
        config=config, tool_call_id=tool_call_id, state=state,
    )
```

- [ ] **Step 9: Delete the now-unused `_call_agent` wrapper**

Remove the one-liner wrapper added in Task 3:

```python
async def _call_agent(agent: str, message: str, skill: str) -> str:
    text, _ = await _call_agent_with_artifact(agent, message, skill)
    return text
```

- [ ] **Step 10: Update `create_health_agent` to pass `state_schema`**

Replace the existing `create_health_agent` function with:

```python
def create_health_agent():
    from langgraph.checkpoint.memory import MemorySaver
    llm = build_llm()
    tools = [
        ask_sleep_agent,
        ask_workout_agent,
        ask_nutrition_agent,
        sync_health_data,
        send_daily_briefing,
    ]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from langgraph.prebuilt import create_react_agent
        return create_react_agent(
            llm,
            tools,
            prompt=_SYSTEM_PROMPT,
            state_schema=HealthAgentState,
            checkpointer=MemorySaver(),
        )
```

- [ ] **Step 11: Run tool tests**

```bash
.venv/bin/pytest tests/orchestrator/test_health_agent_state.py -v
```

Expected: 3 PASS.

- [ ] **Step 12: Run full orchestrator test suite**

```bash
.venv/bin/pytest tests/orchestrator/ -v
```

Expected: all green. If any pre-existing test fails because it mocked `_call_agent`, update it to mock `_call_agent_with_artifact` instead.

- [ ] **Step 13: Commit**

```bash
git add orchestrator/requirements.txt orchestrator/app/health_agent.py \
  tests/orchestrator/test_health_agent_state.py
git commit -m "$(cat <<'EOF'
feat(orchestrator): CoAgent state streaming via copilotkit_emit_state

Tools now emit interim {currentStep, activeAgent, toolCalls[running]}
and return Command(update={..., lastLoggedEntry?}). state_schema on
create_react_agent pipes HealthAgentState through ag_ui_langgraph as
StateSnapshot/StateDelta for useCoAgent on the frontend.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Frontend — types + useCoAgent wiring (no UI yet)

Add type definitions and the hook subscription without new components, so we can verify the data path end-to-end before rendering.

**Files:**
- Modify: `agui-frontend/src/types.ts`
- Modify: `agui-frontend/src/pages/DashboardPage.tsx`

- [ ] **Step 1: Append to `agui-frontend/src/types.ts`**

Add at the bottom of the file:

```ts
export type ToolStatus = "running" | "done" | "error";

export interface ToolCall {
  id: string;
  name: string;
  skill?: string;
  status: ToolStatus;
  startedAt: string;
  endedAt?: string;
  error?: string;
}

export interface LogEntry {
  agent: "sleep" | "workout" | "nutrition";
  skill: string;
  summary: string;
  timestamp: string;
}

export interface HealthAgentState {
  currentStep?: string;
  activeAgent?: "sleep" | "workout" | "nutrition" | null;
  toolCalls?: ToolCall[];
  lastLoggedEntry?: LogEntry | null;
}
```

- [ ] **Step 2: Wire `useCoAgent` in DashboardPage**

Open `agui-frontend/src/pages/DashboardPage.tsx`. At the top, add:

```tsx
import { useCoAgent } from "@copilotkit/react-core";
import type { HealthAgentState } from "../types";
```

Inside the `DashboardPage` component body (before the `return`), add:

```tsx
const { state: agentState } = useCoAgent<HealthAgentState>({ name: "default" });
```

Temporarily add a debug log below it (removed in Task 7):

```tsx
if (agentState) console.debug("[CoAgent]", agentState);
```

- [ ] **Step 3: Smoke-build the frontend**

```bash
cd agui-frontend && npm run build
```

Expected: build succeeds, no type errors.

- [ ] **Step 4: Commit**

```bash
cd ..
git add agui-frontend/src/types.ts agui-frontend/src/pages/DashboardPage.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): subscribe to agent state via useCoAgent

Adds HealthAgentState types and wires useCoAgent<HealthAgentState>
in DashboardPage. No UI changes yet — debug log only, verified
end-to-end in Task 7.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Frontend — AgentStatusBar component (TDD)

**Files:**
- Create: `agui-frontend/src/components/AgentStatusBar.tsx`
- Test: `agui-frontend/src/components/AgentStatusBar.test.tsx`

- [ ] **Step 1: Write failing test**

Create `agui-frontend/src/components/AgentStatusBar.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AgentStatusBar } from "./AgentStatusBar";
import type { ToolCall } from "../types";

const running: ToolCall = {
  id: "t1", name: "ask_workout_agent", skill: "log_workout",
  status: "running", startedAt: "2026-04-15T10:00:00Z",
};
const done: ToolCall = { ...running, id: "t2", status: "done", endedAt: "2026-04-15T10:00:03Z" };

describe("AgentStatusBar", () => {
  it("renders nothing when idle and no running calls", () => {
    const { container } = render(
      <AgentStatusBar currentStep="idle" activeAgent={null} toolCalls={[done]} />
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows currentStep and active agent when running", () => {
    render(
      <AgentStatusBar
        currentStep="querying workout (log_workout)"
        activeAgent="workout"
        toolCalls={[running]}
      />
    );
    expect(screen.getByText(/querying workout/i)).toBeInTheDocument();
    expect(screen.getByText(/workout/i)).toBeInTheDocument();
  });

  it("renders nothing when state is all undefined", () => {
    const { container } = render(<AgentStatusBar />);
    expect(container.firstChild).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd agui-frontend && npx vitest run src/components/AgentStatusBar.test.tsx
```

Expected: FAIL (module not found).

- [ ] **Step 3: Implement component**

Create `agui-frontend/src/components/AgentStatusBar.tsx`:

```tsx
import type { ToolCall } from "../types";

interface Props {
  currentStep?: string;
  activeAgent?: "sleep" | "workout" | "nutrition" | null;
  toolCalls?: ToolCall[];
}

export function AgentStatusBar({ currentStep, activeAgent, toolCalls }: Props) {
  const running = (toolCalls ?? []).filter((t) => t.status === "running");
  const hasActivity =
    running.length > 0 ||
    (currentStep !== undefined && currentStep !== "idle" && currentStep !== "");
  if (!hasActivity) return null;
  return (
    <div
      role="status"
      style={{
        padding: "6px 10px",
        fontSize: 13,
        background: "#eef2ff",
        borderTop: "1px solid #c7d2fe",
      }}
    >
      <span>🔄 {currentStep ?? "working"}</span>
      {activeAgent && (
        <span style={{ marginLeft: 8, opacity: 0.7 }}>· agent: {activeAgent}</span>
      )}
      {running.length > 0 && (
        <span style={{ marginLeft: 8, opacity: 0.7 }}>
          · {running.length} running
        </span>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npx vitest run src/components/AgentStatusBar.test.tsx
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
cd ..
git add agui-frontend/src/components/AgentStatusBar.tsx \
  agui-frontend/src/components/AgentStatusBar.test.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): AgentStatusBar component for live tool-call status

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Frontend — LastLoggedCard component (TDD) + wire to DashboardPage

**Files:**
- Create: `agui-frontend/src/components/LastLoggedCard.tsx`
- Test: `agui-frontend/src/components/LastLoggedCard.test.tsx`
- Modify: `agui-frontend/src/pages/DashboardPage.tsx`

- [ ] **Step 1: Write failing test**

Create `agui-frontend/src/components/LastLoggedCard.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LastLoggedCard } from "./LastLoggedCard";

describe("LastLoggedCard", () => {
  it("renders nothing when entry is null", () => {
    const { container } = render(<LastLoggedCard entry={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when entry is undefined", () => {
    const { container } = render(<LastLoggedCard entry={undefined} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders summary and agent for fresh entry", () => {
    const fresh = new Date().toISOString();
    render(
      <LastLoggedCard
        entry={{ agent: "workout", skill: "log_workout", summary: "30 min run", timestamp: fresh }}
      />
    );
    expect(screen.getByText(/30 min run/)).toBeInTheDocument();
    expect(screen.getByText(/workout/)).toBeInTheDocument();
  });

  it("renders nothing for stale entry older than 30s", () => {
    const stale = new Date(Date.now() - 60_000).toISOString();
    const { container } = render(
      <LastLoggedCard
        entry={{ agent: "sleep", skill: "log_sleep", summary: "slept 8h", timestamp: stale }}
      />
    );
    expect(container.firstChild).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd agui-frontend && npx vitest run src/components/LastLoggedCard.test.tsx
```

Expected: FAIL (module not found).

- [ ] **Step 3: Implement component**

Create `agui-frontend/src/components/LastLoggedCard.tsx`:

```tsx
import type { LogEntry } from "../types";

interface Props {
  entry?: LogEntry | null;
}

const FRESH_MS = 30_000;

export function LastLoggedCard({ entry }: Props) {
  if (!entry) return null;
  const age = Date.now() - new Date(entry.timestamp).getTime();
  if (age > FRESH_MS || age < 0) return null;
  return (
    <div
      role="status"
      style={{
        position: "absolute",
        top: 16,
        right: 16,
        padding: "10px 14px",
        background: "#ecfdf5",
        border: "1px solid #a7f3d0",
        borderRadius: 8,
        fontSize: 13,
        boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
        zIndex: 10,
      }}
    >
      <div style={{ fontWeight: 600 }}>
        ✅ {entry.agent} logged
      </div>
      <div style={{ opacity: 0.8, marginTop: 2 }}>{entry.summary}</div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npx vitest run src/components/LastLoggedCard.test.tsx
```

Expected: 4 PASS.

- [ ] **Step 5: Wire both components in DashboardPage**

Edit `agui-frontend/src/pages/DashboardPage.tsx`. Add imports near the top:

```tsx
import { AgentStatusBar } from "../components/AgentStatusBar";
import { LastLoggedCard } from "../components/LastLoggedCard";
```

Remove the debug line added in Task 5:

```tsx
if (agentState) console.debug("[CoAgent]", agentState);
```

In the JSX around `<CopilotChat ... />`, wrap it with a `position: relative` container and mount the new components. Find the existing chat block and replace with (adjust the wrapper element to match existing layout if different):

```tsx
<div style={{ position: "relative", display: "flex", flexDirection: "column", flex: 1 }}>
  <LastLoggedCard entry={agentState?.lastLoggedEntry} />
  <CopilotChat /* preserve existing props */ />
  <AgentStatusBar
    currentStep={agentState?.currentStep}
    activeAgent={agentState?.activeAgent ?? null}
    toolCalls={agentState?.toolCalls}
  />
</div>
```

- [ ] **Step 6: Full frontend test run + build**

```bash
npx vitest run
npm run build
```

Expected: all PASS, build succeeds.

- [ ] **Step 7: Commit**

```bash
cd ..
git add agui-frontend/src/components/LastLoggedCard.tsx \
  agui-frontend/src/components/LastLoggedCard.test.tsx \
  agui-frontend/src/pages/DashboardPage.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): mount AgentStatusBar + LastLoggedCard in chat

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: End-to-end smoke test (manual)

**Goal:** confirm the loop works in a real docker stack.

- [ ] **Step 1: Export auth and start stack**

```bash
scripts/export-auth.sh
docker compose up --build -d
```

Wait ~20s for all services to become healthy:

```bash
docker compose ps
```

Expected: `orchestrator`, `agent-sleep`, `agent-workout`, `agent-nutrition`, `copilotkit-runtime`, `nginx`, `postgres`, `qdrant` all `healthy` or `running`.

- [ ] **Step 2: Open chat UI**

Visit http://localhost:3000 in a browser. Open DevTools → Console.

- [ ] **Step 3: Send a log-workout message**

Type in the chat: `залогай 30 минут бега`. Observe:

- Within ~100ms: a status bar appears below the chat input with `🔄 querying workout (log_workout) · agent: workout · 1 running`.
- Status bar persists for the duration of the A2A call (~3–5s).
- When the tool finishes: status bar disappears.
- A green toast card appears in the top-right of the chat area: `✅ workout logged — 30 минут бега`. Disappears after 30s (component filter) — in practice remounts will keep it up until next run.
- Chat itself streams the assistant's reply as usual.

- [ ] **Step 4: Send an analyze-nutrition message (no log)**

Type: `как я питался на этой неделе?`. Observe:

- Status bar shows `querying nutrition (analyze_nutrition)`.
- No toast card appears (non-log skill).

- [ ] **Step 5: If smoke test fails — debugging checklist**

- Console error about `useCoAgent` / CopilotKit runtime: confirm `copilotkit-runtime` container is running and mounted at `/copilotkit`. Check agent name parity: frontend uses `"default"`, backend `LangGraphAgent(name="default")`.
- No state events arriving: tail orchestrator logs for `copilotkit_emit_state` errors. Confirm `copilotkit` is installed in the orchestrator container image (rebuild with `--no-cache` if you only `pip install`'d locally).
- `log_entry` artifact missing: tail sub-agent logs for `TaskArtifactUpdateEvent`. Verify the relevant agent executor was rebuilt.
- Tool raises `ValidationError` on `Command`: confirm LangGraph version supports the `InjectedToolCallId` + `InjectedState` pattern (requires `langgraph>=0.2.50`).

- [ ] **Step 6: Bring the stack down**

```bash
docker compose down
```

- [ ] **Step 7: Commit the smoke-test notes**

No code changes from this task. Add a short note to `docs/superpowers/plans/2026-04-15-agent-state-snapshot.md` if any surprise was found during smoke test and a fix was committed.

---

## Task 9: Documentation — update memory

- [ ] **Step 1: Update project memory**

Edit `/Users/oleksandr/.claude/projects/-Users-oleksandr-Documents-life-agents/memory/project_life_agents.md`, find the "Standards-compliance refactor series" section and mark item 4 progress:

Replace:

```
4. **Frontend `useCoAgent` + StateSnapshot** — pending. Replace polling with AG-UI state streaming.
```

with:

```
4a. **Agent state snapshots (CoAgent)** ✅ DONE merged 2026-04-15. Chat UI subscribes via `useCoAgent<HealthAgentState>({name:"default"})` to live {currentStep, activeAgent, toolCalls, lastLoggedEntry}. Backend: tools in `orchestrator/app/health_agent.py` call `copilotkit_emit_state` mid-run and return `Command(update=...)`; `create_react_agent(state_schema=HealthAgentState)`. Sub-agent executors emit a second `log_entry` DataPart artifact for `log_*` skills. Known limit: `MemorySaver` is not durable across restarts — follow-up plan for `PostgresSaver`. Spec: `docs/superpowers/specs/2026-04-15-agent-state-snapshot-design.md`. Plan: `docs/superpowers/plans/2026-04-15-agent-state-snapshot.md`.
4b. **Dashboard push** — deferred. Current HTTP polling of `/stats`, `/agents`, `/health-summary` is standards-valid; revisit only if UX demands it.
```

- [ ] **Step 2: Commit**

```bash
git add /Users/oleksandr/.claude/projects/-Users-oleksandr-Documents-life-agents/memory/project_life_agents.md
git commit -m "$(cat <<'EOF'
docs(memory): mark Plan 4a (CoAgent state snapshots) done

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-review checklist (pre-execution)

- Spec coverage: state schema (Task 2), tool refactor with emit_state + Command (Task 4), artifact extraction (Task 3), sub-agent log_entry (Task 1), frontend types+hook (Task 5), AgentStatusBar (Task 6), LastLoggedCard+wiring (Task 7), smoke test (Task 8), memory update (Task 9). ✅
- `/chat/stream` is **not** removed — telegram bot uses it; spec corrected to reflect this. ✅
- `MemorySaver` kept as known limitation (spec §Known limitations); no migration task. ✅
- `toolCalls` trim to last 20 — implemented in `_trim` helper in Task 4. ✅
- Type consistency: `HealthAgentState` / `ToolCall` / `LogEntry` match between `orchestrator/app/state.py` (Task 2) and `agui-frontend/src/types.ts` (Task 5). ✅
- All steps contain complete code, not placeholders. ✅
