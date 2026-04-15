# Body Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new A2A peer agent `body` so the orchestrator's LLM can answer questions like "сколько я вешу" and "проанализируй историю веса" by routing through a dedicated agent that reads `type='body_composition'` rows in `health_logs`.

**Architecture:** New FastAPI service at port 8004 built 1:1 on the `agents/nutrition` pattern (A2A SDK 0.3.26, `PostgresTaskStore`, Claude via `shared/llm`, summaries into `health_memories`). Ingestion mapping (`sync_service/app/apple_health.py::_METRIC_MAP` + ViHealth payload builders in `telegram_bot/app/vihealth.py` and `sync_service/app/vihealth_pdf.py`) is widened first so BMR, visceral fat, body age, body score, subcutaneous fat %, protein, body water, muscle, body fat kg, fat-free mass reach the DB instead of being dropped. Reverse cross-context: `agents/nutrition/app/prompt.py` and `agents/workout/app/prompt.py` prefetch the latest body row.

**Tech Stack:** Python 3.12, FastAPI, `a2a-sdk==0.3.26`, asyncpg, qdrant-client, `shared/llm` wrapper (Claude CLI), pytest-asyncio.

---

## File Structure

**Create:**
- `agents/body/__init__.py` (empty)
- `agents/body/Dockerfile`
- `agents/body/requirements.txt`
- `agents/body/app/__init__.py` (empty)
- `agents/body/app/main.py` — FastAPI + A2A mount
- `agents/body/app/skills.py` — SKILLS, build_agent_card, SKILL_PROMPTS
- `agents/body/app/prompt.py` — body-composition prompt builder
- `agents/body/app/executor.py` — BodyAgentExecutor (A2A handler)
- `tests/test_body_prompt.py`
- `tests/test_body_skills.py`
- `tests/test_body_executor.py`
- `scripts/smoke-body-agent.sh`

**Modify:**
- `sync_service/app/apple_health.py` — widen `_METRIC_MAP`
- `telegram_bot/app/vihealth.py` — widen `build_sync_payload` mapping
- `sync_service/app/vihealth_pdf.py` — widen `build_payload_from_pdf` mapping
- `shared/shared/db.py` — add `fetch_body_logs`
- `orchestrator/app/health_agent.py` — add `ask_body_agent` tool + register in tools list
- `agents/nutrition/app/prompt.py` — prefetch + include latest body row
- `agents/workout/app/prompt.py` — prefetch + include latest body row
- `telegram_bot/app/main.py` — add `/body` command handler + registration
- `docker-compose.yml` — new `agent-body` service + `AGENT_URLS` addition
- `tests/test_apple_health_mapper.py` — cover new metrics
- `tests/test_nutrition_prompt.py` — cover body-row cross-context
- `tests/test_workout_executor.py` or equivalent — cover body-row cross-context (or add `tests/test_workout_prompt.py` if no prompt tests exist yet)

---

## Task 1: Widen ingestion mapping (sync_service)

**Files:**
- Modify: `sync_service/app/apple_health.py:26-33`
- Test: `tests/test_apple_health_mapper.py`

Currently `map_body_composition` drops ~10 metrics because `_METRIC_MAP` only knows 6 HealthKit names. We introduce invented HealthKit-style names for the ViHealth-only metrics (BMR, visceral fat, body age, etc.) so a single mapping path handles both real Apple Health payloads and ViHealth-derived payloads.

- [ ] **Step 1: Add failing test for widened mapping**

Append to `tests/test_apple_health_mapper.py`:

```python
def test_map_body_composition_widened_metrics():
    from sync_service.app.apple_health import map_body_composition
    payload = {
        "data": [
            {"date": "2026-04-14 09:37:16 +0000", "qty": 79.6, "name": "Body Mass", "units": "kg"},
            {"date": "2026-04-14 09:37:16 +0000", "qty": 1633, "name": "Basal Metabolic Rate", "units": "kcal"},
            {"date": "2026-04-14 09:37:16 +0000", "qty": 8, "name": "Visceral Fat Grade", "units": "count"},
            {"date": "2026-04-14 09:37:16 +0000", "qty": 32, "name": "Body Age", "units": "count"},
            {"date": "2026-04-14 09:37:16 +0000", "qty": 73, "name": "Body Score", "units": "count"},
            {"date": "2026-04-14 09:37:16 +0000", "qty": 18.9, "name": "Subcutaneous Fat Percentage", "units": "%"},
            {"date": "2026-04-14 09:37:16 +0000", "qty": 11.7, "name": "Protein Mass", "units": "kg"},
            {"date": "2026-04-14 09:37:16 +0000", "qty": 42.9, "name": "Body Water", "units": "kg"},
            {"date": "2026-04-14 09:37:16 +0000", "qty": 54.6, "name": "Muscle Mass", "units": "kg"},
            {"date": "2026-04-14 09:37:16 +0000", "qty": 21.1, "name": "Body Fat Mass", "units": "kg"},
            {"date": "2026-04-14 09:37:16 +0000", "qty": 58.5, "name": "Fat Free Body Weight", "units": "kg"},
        ],
    }
    rows = map_body_composition(payload)
    assert len(rows) == 1
    data = rows[0]["data"]
    assert data["weight_kg"] == 79.6
    assert data["bmr_kcal"] == 1633.0
    assert data["visceral_fat_grade"] == 8.0
    assert data["body_age"] == 32.0
    assert data["body_score"] == 73.0
    assert data["subcutaneous_fat_pct"] == 18.9
    assert data["protein_kg"] == 11.7
    assert data["body_water_kg"] == 42.9
    assert data["muscle_kg"] == 54.6
    assert data["body_fat_kg"] == 21.1
    assert data["fat_free_kg"] == 58.5
```

- [ ] **Step 2: Run it, expect failure**

```bash
pytest tests/test_apple_health_mapper.py::test_map_body_composition_widened_metrics -v
```
Expected: FAIL — new keys absent from `rows[0]["data"]`.

- [ ] **Step 3: Widen `_METRIC_MAP`**

Replace lines 26–33 of `sync_service/app/apple_health.py` with:

```python
_METRIC_MAP: dict[str, str] = {
    "Body Mass": "weight_kg",
    "Body Fat Percentage": "body_fat_pct",
    "Lean Body Mass": "lean_mass_kg",
    "Body Mass Index": "bmi",
    "Skeletal Muscle Mass": "skeletal_muscle_kg",
    "Bone Mass": "bone_mass_kg",
    # ViHealth-derived metrics (invented HealthKit-style names kept stable)
    "Basal Metabolic Rate": "bmr_kcal",
    "Visceral Fat Grade": "visceral_fat_grade",
    "Body Age": "body_age",
    "Body Score": "body_score",
    "Subcutaneous Fat Percentage": "subcutaneous_fat_pct",
    "Protein Mass": "protein_kg",
    "Body Water": "body_water_kg",
    "Muscle Mass": "muscle_kg",
    "Body Fat Mass": "body_fat_kg",
    "Fat Free Body Weight": "fat_free_kg",
}
```

Also update the module docstring (lines 12–18) to list the new supported names.

- [ ] **Step 4: Run test, expect pass**

```bash
pytest tests/test_apple_health_mapper.py -v
```
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add sync_service/app/apple_health.py tests/test_apple_health_mapper.py
git commit -m "feat(sync): widen body-composition metric mapping for ViHealth fields"
```

---

## Task 2: Widen ViHealth payload builders

**Files:**
- Modify: `telegram_bot/app/vihealth.py:128-154` (`build_sync_payload`)
- Modify: `sync_service/app/vihealth_pdf.py:119-151` (`build_payload_from_pdf`)

The Vision parser already extracts the richer set; we just need `build_sync_payload` / `build_payload_from_pdf` to emit them.

- [ ] **Step 1: Add failing test**

Create `tests/test_vihealth_payload.py`:

```python
from datetime import datetime, timezone
from unittest.mock import patch


def test_build_sync_payload_emits_widened_fields():
    """build_sync_payload maps all metrics the parser extracts."""
    from telegram_bot.app.vihealth import build_sync_payload

    fake_parse = {
        "recorded_at": datetime(2026, 4, 14, 9, 37, 16, tzinfo=timezone.utc),
        "metrics": {
            "weight_kg": 79.6, "body_fat_pct": 26.5, "bmi": 27.5,
            "skeletal_muscle_kg": 33.1, "bone_mass_kg": 3.9,
            "body_fat_kg": 21.1, "protein_kg": 11.7, "body_water_kg": 42.9,
            "muscle_kg": 54.6, "visceral_fat_grade": 8,
            "bmr_kcal": 1633, "fat_free_kg": 58.5,
            "subcutaneous_fat_pct": 18.9, "body_age": 32, "body_score": 73,
        },
    }

    with patch("telegram_bot.app.vihealth.parse_vihealth_pdf_vision", return_value=fake_parse):
        payload = build_sync_payload(b"ignored")

    names = {e["name"] for e in payload["data"]}
    for required in {
        "Body Mass", "Body Fat Percentage", "Body Mass Index",
        "Skeletal Muscle Mass", "Bone Mass", "Lean Body Mass",
        "Basal Metabolic Rate", "Visceral Fat Grade", "Body Age",
        "Body Score", "Subcutaneous Fat Percentage", "Protein Mass",
        "Body Water", "Muscle Mass", "Body Fat Mass", "Fat Free Body Weight",
    }:
        assert required in names, f"missing {required}"
```

- [ ] **Step 2: Run it, expect failure**

```bash
pytest tests/test_vihealth_payload.py -v
```
Expected: FAIL — only 6 names emitted.

- [ ] **Step 3: Update `build_sync_payload` in `telegram_bot/app/vihealth.py`**

Replace the `mapping` dict (line 136) and the code through `return {"data": data}` with:

```python
    mapping = {
        "weight_kg": ("Body Mass", "kg"),
        "body_fat_pct": ("Body Fat Percentage", "%"),
        "bmi": ("Body Mass Index", "count"),
        "skeletal_muscle_kg": ("Skeletal Muscle Mass", "kg"),
        "bone_mass_kg": ("Bone Mass", "kg"),
        "bmr_kcal": ("Basal Metabolic Rate", "kcal"),
        "visceral_fat_grade": ("Visceral Fat Grade", "count"),
        "body_age": ("Body Age", "count"),
        "body_score": ("Body Score", "count"),
        "subcutaneous_fat_pct": ("Subcutaneous Fat Percentage", "%"),
        "protein_kg": ("Protein Mass", "kg"),
        "body_water_kg": ("Body Water", "kg"),
        "muscle_kg": ("Muscle Mass", "kg"),
        "body_fat_kg": ("Body Fat Mass", "kg"),
        "fat_free_kg": ("Fat Free Body Weight", "kg"),
    }

    if "weight_kg" in metrics and "body_fat_kg" in metrics and "lean_mass_kg" not in metrics:
        metrics["lean_mass_kg"] = round(metrics["weight_kg"] - metrics["body_fat_kg"], 2)
    mapping["lean_mass_kg"] = ("Lean Body Mass", "kg")

    data = [
        {"date": date_str, "qty": metrics[key], "name": name, "units": units}
        for key, (name, units) in mapping.items()
        if key in metrics
    ]
    return {"data": data}
```

- [ ] **Step 4: Apply the identical mapping to `sync_service/app/vihealth_pdf.py::build_payload_from_pdf`**

Replace the `reverse_map` dict on lines 131–138 and the data-assembly block with the exact same `mapping` dict and loop as Step 3. Keep the lean-mass derivation.

- [ ] **Step 5: Run tests, expect pass**

```bash
pytest tests/test_vihealth_payload.py tests/test_apple_health_mapper.py -v
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add telegram_bot/app/vihealth.py sync_service/app/vihealth_pdf.py tests/test_vihealth_payload.py
git commit -m "feat(ingest): emit all ViHealth metrics to /sync/body"
```

---

## Task 3: Add `fetch_body_logs` helper

**Files:**
- Modify: `shared/shared/db.py`
- Test: `tests/test_body_db.py`

Historical body rows were written with `agent='workout'` (by `map_body_composition`). To be robust, the helper filters by `type='body_composition'` regardless of the `agent` column — no migration needed.

- [ ] **Step 1: Add failing test**

Create `tests/test_body_db.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_fetch_body_logs_filters_by_type():
    from shared.db import fetch_body_logs

    fake_pool = AsyncMock()
    fake_pool.fetch.return_value = [
        {"type": "body_composition", "data": {"weight_kg": 79.6},
         "recorded_at": "2026-04-14", "source": "vihealth"},
    ]

    with patch("shared.db.get_pool", new=AsyncMock(return_value=fake_pool)):
        rows = await fetch_body_logs(limit=5)

    assert len(rows) == 1
    assert rows[0]["data"]["weight_kg"] == 79.6
    call_sql = fake_pool.fetch.call_args.args[0]
    assert "type = $1" in call_sql or "type=$1" in call_sql.replace(" ", "=")
    assert fake_pool.fetch.call_args.args[1] == "body_composition"
```

- [ ] **Step 2: Run it, expect failure**

```bash
pytest tests/test_body_db.py -v
```
Expected: FAIL — `fetch_body_logs` does not exist.

- [ ] **Step 3: Add helper to `shared/shared/db.py`**

Append to the file:

```python
async def fetch_body_logs(limit: int = 30) -> list[dict]:
    """Return latest body_composition rows regardless of the `agent` column.

    Historical rows were written with agent='workout' by map_body_composition;
    new rows may land under agent='body'. Filter purely by type to tolerate both.
    """
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT type, data, recorded_at, source FROM health_logs "
        "WHERE type = $1 ORDER BY recorded_at DESC LIMIT $2",
        "body_composition", limit,
    )
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Run test, expect pass**

```bash
pytest tests/test_body_db.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shared/shared/db.py tests/test_body_db.py
git commit -m "feat(shared): add fetch_body_logs helper"
```

---

## Task 4: Body-agent prompt builder

**Files:**
- Create: `agents/body/__init__.py` (empty)
- Create: `agents/body/app/__init__.py` (empty)
- Create: `agents/body/app/prompt.py`
- Test: `tests/test_body_prompt.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_body_prompt.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone


@pytest.fixture
def body_row():
    return {
        "type": "body_composition",
        "source": "vihealth",
        "recorded_at": datetime(2026, 4, 14, 9, 37, 16, tzinfo=timezone.utc),
        "data": {
            "weight_kg": 79.6, "body_fat_pct": 26.5, "muscle_kg": 54.6,
            "skeletal_muscle_kg": 33.1, "bmr_kcal": 1633,
            "visceral_fat_grade": 8, "body_age": 32, "body_score": 73,
        },
    }


@pytest.mark.asyncio
async def test_get_latest_body_includes_weight(body_row):
    with patch("agents.body.app.prompt.fetch_body_logs", new=AsyncMock(return_value=[body_row])), \
         patch("agents.body.app.prompt.fetch_recent_logs", new=AsyncMock(return_value=[])), \
         patch("agents.body.app.prompt.search_memories", new=AsyncMock(return_value=[])):
        from agents.body.app.prompt import build_body_prompt
        prompt = await build_body_prompt("get_latest_body", {})

    assert "79.6" in prompt
    assert "26.5" in prompt
    assert "get_latest_body" in prompt


@pytest.mark.asyncio
async def test_analyze_body_trend_pulls_cross_context(body_row):
    with patch("agents.body.app.prompt.fetch_body_logs", new=AsyncMock(return_value=[body_row])) as mb, \
         patch("agents.body.app.prompt.fetch_recent_logs", new=AsyncMock(return_value=[])) as mr, \
         patch("agents.body.app.prompt.search_memories", new=AsyncMock(return_value=[])):
        from agents.body.app.prompt import build_body_prompt
        await build_body_prompt("analyze_body_trend", {})

    assert mb.called
    agents = {c.args[0] for c in mr.call_args_list}
    assert {"nutrition", "workout"}.issubset(agents)


@pytest.mark.asyncio
async def test_body_prompt_handles_empty_data():
    with patch("agents.body.app.prompt.fetch_body_logs", new=AsyncMock(return_value=[])), \
         patch("agents.body.app.prompt.fetch_recent_logs", new=AsyncMock(return_value=[])), \
         patch("agents.body.app.prompt.search_memories", new=AsyncMock(return_value=[])):
        from agents.body.app.prompt import build_body_prompt
        prompt = await build_body_prompt("get_latest_body", {})

    assert "No body composition" in prompt or "no body" in prompt.lower()
```

- [ ] **Step 2: Run tests, expect failure (module missing)**

```bash
pytest tests/test_body_prompt.py -v
```
Expected: ImportError.

- [ ] **Step 3: Create `agents/body/app/prompt.py`**

```python
from shared.db import fetch_body_logs, fetch_recent_logs
from shared.vector import search_memories


def _format_body(r: dict) -> str:
    date = r["recorded_at"].date()
    d = r.get("data", {})
    parts = [
        f"weight={d.get('weight_kg')}kg",
        f"fat={d.get('body_fat_pct')}%",
        f"muscle={d.get('muscle_kg')}kg",
        f"skeletal_muscle={d.get('skeletal_muscle_kg')}kg",
        f"bmr={d.get('bmr_kcal')}kcal",
        f"visceral_fat={d.get('visceral_fat_grade')}",
        f"body_age={d.get('body_age')}",
        f"body_score={d.get('body_score')}",
    ]
    return f"- {date} | " + " | ".join(p for p in parts if "None" not in p)


def _format_cross(r: dict) -> str:
    return f"- {r['recorded_at'].date()} | {r['type']} | {r.get('data', {})}"


async def build_body_prompt(task: str, params: dict) -> str:
    body_logs = await fetch_body_logs(limit=30)
    memories = await search_memories(task, limit=5)

    if task == "analyze_body_trend":
        nutrition_logs = await fetch_recent_logs("nutrition", limit=20)
        workout_logs = await fetch_recent_logs("workout", limit=20)
    else:
        nutrition_logs = []
        workout_logs = []

    body_text = "\n".join(_format_body(r) for r in body_logs) \
        or "No body composition measurements yet — ask the user to upload a ViHealth PDF."

    nutrition_text = "\n".join(_format_cross(r) for r in nutrition_logs) \
        or "No recent nutrition logs."
    workout_text = "\n".join(_format_cross(r) for r in workout_logs) \
        or "No recent workout logs."

    memories_text = "\n".join(f"- {m.get('text', '')}" for m in memories) \
        or "No relevant memories."

    return f"""You are a personal body-composition assistant. You have access to the user's weigh-in history and context from peer agents.

## Body composition history (latest 30):
{body_text}

## Recent nutrition (cross-context):
{nutrition_text}

## Recent workouts (cross-context):
{workout_text}

## Relevant memories:
{memories_text}

## User request:
Task: {task}
Params: {params}

Respond in the user's language. Be concise and specific, reference actual numbers.
For get_latest_body: state the most recent weight, body fat %, and any standouts (score, visceral fat) in 1-3 sentences.
For analyze_body_trend: look at the weight/fat/muscle trend, correlate with calorie intake and training volume, and give 1-2 concrete recommendations.
If there is no body data, say so clearly and ask the user to upload a ViHealth PDF."""
```

- [ ] **Step 4: Run tests, expect pass**

```bash
pytest tests/test_body_prompt.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/body/__init__.py agents/body/app/__init__.py agents/body/app/prompt.py tests/test_body_prompt.py
git commit -m "feat(body): prompt builder for body composition agent"
```

---

## Task 5: Body-agent skills declaration

**Files:**
- Create: `agents/body/app/skills.py`
- Test: `tests/test_body_skills.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_body_skills.py`:

```python
def test_body_skills_list():
    from agents.body.app.skills import SKILLS, SKILL_PROMPTS
    ids = {s.id for s in SKILLS}
    assert ids == {"get_latest_body", "analyze_body_trend"}
    assert set(SKILL_PROMPTS.keys()) == ids


def test_body_agent_card_has_protocol_03():
    from agents.body.app.skills import build_agent_card
    card = build_agent_card()
    assert card.protocol_version == "0.3.0"
    assert card.name == "body-agent"
    assert len(card.skills) == 2
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_body_skills.py -v
```
Expected: ImportError.

- [ ] **Step 3: Create `agents/body/app/skills.py`**

```python
"""Body agent skill declarations + per-skill prompt builders."""
from __future__ import annotations

import os
from typing import Awaitable, Callable

from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from .prompt import build_body_prompt


SKILLS: list[AgentSkill] = [
    AgentSkill(
        id="get_latest_body",
        name="Get Latest Body Composition",
        description="Return the most recent weight, body fat %, muscle and related metrics.",
        tags=["body", "weight", "query"],
        examples=["сколько я вешу", "what's my weight", "current body fat"],
    ),
    AgentSkill(
        id="analyze_body_trend",
        name="Analyze Body Trend",
        description="Analyze weight / fat / muscle dynamics and correlate with nutrition and training.",
        tags=["body", "analysis"],
        examples=["проанализируй историю веса", "how has my body composition changed"],
    ),
]


def build_agent_card() -> AgentCard:
    url = os.environ.get("BODY_AGENT_URL", "http://agent-body:8004/")
    return AgentCard(
        protocol_version="0.3.0",
        name="body-agent",
        description=(
            "Owns body-composition data (weight, fat %, muscle, BMR, visceral fat, body age) "
            "ingested from ViHealth/LePulse scales. Answers current-state queries and trend analyses."
        ),
        url=url,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=SKILLS,
    )


PromptFn = Callable[[str, dict], Awaitable[str]]


async def _prompt_get_latest(message: str, params: dict) -> str:
    return await build_body_prompt("get_latest_body", {**params, "message": message})


async def _prompt_analyze(message: str, params: dict) -> str:
    return await build_body_prompt("analyze_body_trend", {**params, "message": message})


SKILL_PROMPTS: dict[str, PromptFn] = {
    "get_latest_body": _prompt_get_latest,
    "analyze_body_trend": _prompt_analyze,
}
```

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_body_skills.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/body/app/skills.py tests/test_body_skills.py
git commit -m "feat(body): skill declarations and agent card"
```

---

## Task 6: Body-agent executor

**Files:**
- Create: `agents/body/app/executor.py`
- Test: `tests/test_body_executor.py`

Executor mirrors `agents/nutrition/app/executor.py` but has no `log_*` skills (no log_entry artifacts, no Yazio sync trigger, no peer-agent fan-out — cross-context is handled inside the prompt builder).

- [ ] **Step 1: Write failing test**

Create `tests/test_body_executor.py`:

```python
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from a2a.types import Message, Part, Role, TextPart, TaskState


class _Ctx:
    def __init__(self, text: str, skill: str | None = None):
        self.task_id = "t1"
        self.context_id = "c1"
        self.message = Message(
            role=Role.user,
            parts=[Part(root=TextPart(text=text))],
            message_id="m1",
            metadata={"skillId": skill} if skill else None,
        )


class _Queue:
    def __init__(self):
        self.events = []

    async def enqueue_event(self, evt):
        self.events.append(evt)


@pytest.mark.asyncio
async def test_executor_runs_get_latest_body_skill():
    from agents.body.app.executor import BodyAgentExecutor

    fake_llm = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content="Weight: 79.6 kg")))

    with patch("agents.body.app.executor._get_llm", return_value=fake_llm), \
         patch("agents.body.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.body.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.body.app.prompt.fetch_body_logs", new=AsyncMock(return_value=[])), \
         patch("agents.body.app.prompt.fetch_recent_logs", new=AsyncMock(return_value=[])), \
         patch("agents.body.app.prompt.search_memories", new=AsyncMock(return_value=[])):
        ctx = _Ctx("сколько я вешу", skill="get_latest_body")
        q = _Queue()
        await BodyAgentExecutor().execute(ctx, q)

    states = [getattr(e, "status", None) and e.status.state for e in q.events if hasattr(e, "status")]
    assert TaskState.completed in states


@pytest.mark.asyncio
async def test_executor_fails_gracefully_on_unknown_skill():
    from agents.body.app.executor import BodyAgentExecutor

    fake_llm = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content="garbage")))
    with patch("agents.body.app.executor._get_llm", return_value=fake_llm):
        ctx = _Ctx("??? nonsense ???", skill=None)
        q = _Queue()
        await BodyAgentExecutor().execute(ctx, q)

    failed_states = [
        e.status.state for e in q.events
        if hasattr(e, "status") and e.status.state == TaskState.failed
    ]
    assert failed_states, "expected failed status when skill cannot be inferred"
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_body_executor.py -v
```
Expected: ImportError.

- [ ] **Step 3: Create `agents/body/app/executor.py`**

```python
"""BodyAgentExecutor — maps incoming A2A messages to body-domain skills."""
from __future__ import annotations

import json
import logging
import uuid

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    Artifact, Message, Part, Role, TaskArtifactUpdateEvent,
    TaskState, TaskStatus, TaskStatusUpdateEvent, TextPart,
)
from langchain_core.messages import HumanMessage

from shared.llm import build_llm
from shared.vector import upsert_memory
from shared.db import insert_task_record

from .skills import SKILL_PROMPTS

_LLM = None
logger = logging.getLogger(__name__)


def _get_llm():
    global _LLM
    if _LLM is None:
        _LLM = build_llm()
    return _LLM


def _extract_text(ctx: RequestContext) -> str:
    if ctx.message is None:
        return ""
    out = []
    for p in ctx.message.parts or []:
        root = getattr(p, "root", p)
        text = getattr(root, "text", None)
        if text:
            out.append(text)
    return "\n".join(out)


def _metadata_skill(ctx: RequestContext) -> str | None:
    meta = getattr(ctx.message, "metadata", None) if ctx.message else None
    if not meta:
        return None
    sid = meta.get("skillId") if isinstance(meta, dict) else getattr(meta, "skillId", None)
    return sid if sid in SKILL_PROMPTS else None


def _params_from_metadata(ctx: RequestContext) -> dict:
    meta = getattr(ctx.message, "metadata", None) if ctx.message else None
    if isinstance(meta, dict):
        extra = meta.get("params")
        return dict(extra) if isinstance(extra, dict) else {}
    return {}


async def _infer_skill_via_llm(message: str) -> str | None:
    known = ", ".join(SKILL_PROMPTS.keys())
    prompt = (
        "Pick exactly one skill ID for this user message. "
        f"Valid IDs: {known}. Respond with the ID only.\n\nMessage: {message}"
    )
    try:
        result = await _get_llm().ainvoke([HumanMessage(prompt)])
        raw = result.content if isinstance(result.content, str) else str(result.content)
    except Exception as e:
        logger.warning("LLM skill inference failed: %s", e)
        return None
    token = raw.strip().split()[0] if raw else ""
    return token if token in SKILL_PROMPTS else None


class BodyAgentExecutor(AgentExecutor):
    async def execute(self, ctx: RequestContext, event_queue: EventQueue) -> None:
        task_id = ctx.task_id or str(uuid.uuid4())
        context_id = ctx.context_id or str(uuid.uuid4())
        message = _extract_text(ctx)
        skill_id = _metadata_skill(ctx) or await _infer_skill_via_llm(message)

        await _emit_status(event_queue, task_id, context_id, TaskState.working)

        if skill_id is None or skill_id not in SKILL_PROMPTS:
            await _emit_status(
                event_queue, task_id, context_id, TaskState.failed,
                error="cannot determine skill", final=True,
            )
            return

        try:
            params = _params_from_metadata(ctx)
            params.setdefault("message", message)
            prompt = await SKILL_PROMPTS[skill_id](message, params)
            result = await _get_llm().ainvoke([HumanMessage(prompt)])
            output = result.content if isinstance(result.content, str) else str(result.content)

            await insert_task_record(
                agent="body", task_id=task_id, context_id=context_id,
                skill_id=skill_id, input_=params, output=output, state="completed",
            )
            await upsert_memory(
                agent_id="body",
                id_=str(uuid.uuid4()),
                text=output,
                metadata={"skill": skill_id, "params": json.dumps(params)},
            )

            await _emit_artifact(event_queue, task_id, context_id, "analysis", output)
            await _emit_status(event_queue, task_id, context_id, TaskState.completed, final=True)

        except Exception as e:
            logger.exception("body executor failed")
            await _emit_status(
                event_queue, task_id, context_id, TaskState.failed,
                error=str(e), final=True,
            )

    async def cancel(self, ctx: RequestContext, event_queue: EventQueue) -> None:
        await _emit_status(event_queue, ctx.task_id, ctx.context_id, TaskState.canceled, final=True)


def _error_message(text: str) -> Message:
    return Message(
        role=Role.agent,
        parts=[Part(root=TextPart(text=text))],
        message_id=str(uuid.uuid4()),
    )


async def _emit_status(event_queue: EventQueue, task_id: str, context_id: str,
                       state: TaskState, error: str | None = None, final: bool = False) -> None:
    status = TaskStatus(state=state)
    if error:
        status.message = _error_message(error)
    await event_queue.enqueue_event(TaskStatusUpdateEvent(
        task_id=task_id, context_id=context_id, status=status, final=final,
    ))


async def _emit_artifact(event_queue: EventQueue, task_id: str, context_id: str,
                         name: str, text: str) -> None:
    artifact = Artifact(
        artifact_id=str(uuid.uuid4()),
        name=name,
        parts=[Part(root=TextPart(text=text))],
    )
    await event_queue.enqueue_event(TaskArtifactUpdateEvent(
        task_id=task_id, context_id=context_id, artifact=artifact,
        append=False, last_chunk=True,
    ))
```

- [ ] **Step 4: Run tests, expect pass**

```bash
pytest tests/test_body_executor.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/body/app/executor.py tests/test_body_executor.py
git commit -m "feat(body): A2A executor for body agent"
```

---

## Task 7: Body-agent HTTP entrypoint + Dockerfile

**Files:**
- Create: `agents/body/app/main.py`
- Create: `agents/body/Dockerfile`
- Create: `agents/body/requirements.txt`

- [ ] **Step 1: Create `agents/body/app/main.py`**

```python
"""Body agent HTTP entrypoint."""
import logging

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from fastapi import FastAPI

from shared.a2a_store import PostgresTaskStore

from .executor import BodyAgentExecutor
from .skills import build_agent_card

logger = logging.getLogger(__name__)

app = FastAPI(title="Body Agent")


@app.get("/health")
async def health():
    return {"status": "ok"}


def _build_a2a_app() -> A2AStarletteApplication:
    handler = DefaultRequestHandler(
        agent_executor=BodyAgentExecutor(),
        task_store=PostgresTaskStore(agent="body"),
    )
    return A2AStarletteApplication(agent_card=build_agent_card(), http_handler=handler)


app.mount("/", _build_a2a_app().build())
```

- [ ] **Step 2: Create `agents/body/requirements.txt`**

Copy the exact content of `agents/nutrition/requirements.txt`:

```bash
cp agents/nutrition/requirements.txt agents/body/requirements.txt
```

- [ ] **Step 3: Create `agents/body/Dockerfile`**

Copy the nutrition Dockerfile and change the port + paths:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g @anthropic-ai/claude-code && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY agents/body/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ /shared
RUN pip install --no-cache-dir -e /shared

COPY agents/body/app/ ./app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
```

- [ ] **Step 4: Verify the container builds locally**

```bash
docker build -f agents/body/Dockerfile -t agent-body-test .
```
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add agents/body/Dockerfile agents/body/requirements.txt agents/body/app/main.py
git commit -m "feat(body): Dockerfile, requirements, and HTTP entrypoint"
```

---

## Task 8: docker-compose service entry

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add `agent-body` service**

Copy the `agent-nutrition` block (lines matching `agent-nutrition:` through its `start_period: 30s`) and paste a new block below it with these substitutions:
- service name: `agent-body`
- Dockerfile: `agents/body/Dockerfile`
- port: `8004:8004`
- healthcheck URL: `http://localhost:8004/health`

Example:

```yaml
  agent-body:
    build:
      context: .
      dockerfile: agents/body/Dockerfile
    env_file:
      - .env
      - .env.auth
    environment:
      POSTGRES_DSN: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      QDRANT_HOST: ${QDRANT_HOST}
      QDRANT_PORT: ${QDRANT_PORT}
      GEMINI_API_KEY: ${GEMINI_API_KEY}
    volumes:
      - ~/.claude:/root/.claude:ro
      - ~/.claude.json:/root/.claude.json:ro
    ports:
      - "8004:8004"
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8004/health"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
```

- [ ] **Step 2: Update `AGENT_URLS` in the orchestrator env**

Find the orchestrator service's `AGENT_URLS` line (around line 130) and append `,http://agent-body:8004`.

- [ ] **Step 3: Verify compose parses**

```bash
docker compose config --services | grep agent-body
```
Expected: output includes `agent-body`.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(compose): register agent-body service"
```

---

## Task 9: Orchestrator `ask_body_agent` tool

**Files:**
- Modify: `orchestrator/app/health_agent.py`
- Test: `tests/test_orchestrator_tools.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_orchestrator_tools.py` (or create if its shape differs):

```python
def test_health_agent_exposes_ask_body_agent():
    from orchestrator.app.health_agent import ask_body_agent
    assert ask_body_agent is not None
    # LangChain tool name metadata
    assert ask_body_agent.name == "ask_body_agent"
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_orchestrator_tools.py::test_health_agent_exposes_ask_body_agent -v
```
Expected: ImportError / AttributeError.

- [ ] **Step 3: Add the tool to `orchestrator/app/health_agent.py`**

Right after the existing `ask_nutrition_agent` definition (around line 207), insert:

```python
@tool
async def ask_body_agent(
    message: str,
    skill: Literal["get_latest_body", "analyze_body_trend"],
    config: RunnableConfig,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[HealthAgentState, InjectedState],
) -> Command:
    """Call body-agent. Skills: get_latest_body (current weight/fat/muscle snapshot) or
    analyze_body_trend (dynamics with nutrition/workout correlation)."""
    return await _run_peer_tool(
        agent="body", message=message, skill=skill, tool_name="ask_body_agent",
        config=config, tool_call_id=tool_call_id, state=state,
    )
```

Then widen the `agent` parameter type on `_run_peer_tool` (around line 117) — change

```python
agent: Literal["sleep", "workout", "nutrition"],
```

to

```python
agent: Literal["sleep", "workout", "nutrition", "body"],
```

And add `ask_body_agent` to the `tools` list in `create_health_agent()` (around line 248):

```python
    tools = [
        ask_sleep_agent,
        ask_workout_agent,
        ask_nutrition_agent,
        ask_body_agent,
        sync_health_data,
        send_daily_briefing,
    ]
```

Update the system prompt (line 238) to mention the fourth peer:

```python
_SYSTEM_PROMPT = (
    "You are a personal health assistant. You have four peer agents: sleep, workout, nutrition, body. "
    "Each tool accepts a skill parameter — pick the one that matches intent (log/analyze/recommend/query). "
    "For sync or briefing requests, use the dedicated tools. Be concise and actionable."
)
```

- [ ] **Step 4: Run tests, expect pass**

```bash
pytest tests/test_orchestrator_tools.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/app/health_agent.py tests/test_orchestrator_tools.py
git commit -m "feat(orchestrator): ask_body_agent tool"
```

---

## Task 10: Reverse cross-context — nutrition prompt reads body

**Files:**
- Modify: `agents/nutrition/app/prompt.py`
- Test: `tests/test_nutrition_prompt.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_nutrition_prompt.py`:

```python
@pytest.mark.asyncio
async def test_nutrition_prompt_includes_latest_body_row():
    from datetime import datetime, timezone

    body_row = {
        "type": "body_composition",
        "recorded_at": datetime(2026, 4, 14, 9, 37, 16, tzinfo=timezone.utc),
        "data": {"weight_kg": 79.6, "bmr_kcal": 1633, "body_fat_pct": 26.5},
        "source": "vihealth",
    }
    with patch("agents.nutrition.app.prompt.fetch_recent_logs", new_callable=AsyncMock) as mock_logs, \
         patch("agents.nutrition.app.prompt.search_memories", new_callable=AsyncMock) as mock_mem, \
         patch("agents.nutrition.app.prompt.fetch_body_logs", new_callable=AsyncMock, return_value=[body_row]):
        mock_logs.return_value = []
        mock_mem.return_value = []

        from agents.nutrition.app.prompt import build_nutrition_prompt
        result = await build_nutrition_prompt("get_recommendations", {})

    assert "1633" in result  # BMR should appear
    assert "79.6" in result  # weight should appear
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_nutrition_prompt.py::test_nutrition_prompt_includes_latest_body_row -v
```
Expected: FAIL — BMR/weight not referenced.

- [ ] **Step 3: Update `agents/nutrition/app/prompt.py`**

At the top add:

```python
from shared.db import fetch_body_logs
```

Inside `build_nutrition_prompt` (after existing prefetches), add:

```python
    body_rows = await fetch_body_logs(limit=1)
```

Build a short body line:

```python
    if body_rows:
        d = body_rows[0]["data"]
        date = body_rows[0]["recorded_at"].date()
        body_text = (
            f"- {date} | weight={d.get('weight_kg')}kg "
            f"| fat={d.get('body_fat_pct')}% | BMR={d.get('bmr_kcal')}kcal"
        )
    else:
        body_text = "No body composition measurements yet."
```

And insert a new section into the returned prompt string, immediately before `## Relevant memories:`:

```
## Latest body composition (cross-context):
{body_text}

```

- [ ] **Step 4: Run tests, expect pass**

```bash
pytest tests/test_nutrition_prompt.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/nutrition/app/prompt.py tests/test_nutrition_prompt.py
git commit -m "feat(nutrition): cross-context include latest body composition"
```

---

## Task 11: Reverse cross-context — workout prompt reads body

**Files:**
- Modify: `agents/workout/app/prompt.py`
- Test: new `tests/test_workout_prompt.py` (if none exists) or extend existing

- [ ] **Step 1: Inspect workout prompt structure**

```bash
ls tests/ | grep workout
cat agents/workout/app/prompt.py | head -60
```

Use the same pattern as nutrition. If `tests/test_workout_prompt.py` doesn't exist, create it; otherwise append.

- [ ] **Step 2: Write failing test** (pattern mirrors Task 10 Step 1 — replace `nutrition` with `workout`)

```python
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_workout_prompt_includes_latest_body_row():
    body_row = {
        "type": "body_composition",
        "recorded_at": datetime(2026, 4, 14, 9, 37, 16, tzinfo=timezone.utc),
        "data": {"weight_kg": 79.6, "lean_mass_kg": 58.5, "body_fat_pct": 26.5},
        "source": "vihealth",
    }
    with patch("agents.workout.app.prompt.fetch_recent_logs", new_callable=AsyncMock) as mock_logs, \
         patch("agents.workout.app.prompt.search_memories", new_callable=AsyncMock) as mock_mem, \
         patch("agents.workout.app.prompt.fetch_body_logs", new_callable=AsyncMock, return_value=[body_row]):
        mock_logs.return_value = []
        mock_mem.return_value = []

        from agents.workout.app.prompt import build_workout_prompt
        result = await build_workout_prompt("get_recommendations", {})

    assert "79.6" in result or "58.5" in result
```

(Adjust the import / function name to match `agents/workout/app/prompt.py`'s actual signature.)

- [ ] **Step 3: Run, expect failure**

```bash
pytest tests/test_workout_prompt.py -v
```

- [ ] **Step 4: Modify `agents/workout/app/prompt.py`**

Apply the same change as Task 10 Step 3: import `fetch_body_logs`, prefetch `body_rows = await fetch_body_logs(limit=1)`, render a body section, inject it into the returned prompt. Emphasize `lean_mass_kg` / `weight_kg` which are the fields workout recommendations care about.

- [ ] **Step 5: Run, expect pass**

```bash
pytest tests/test_workout_prompt.py -v
```

- [ ] **Step 6: Commit**

```bash
git add agents/workout/app/prompt.py tests/test_workout_prompt.py
git commit -m "feat(workout): cross-context include latest body composition"
```

---

## Task 12: Telegram `/body` command

**Files:**
- Modify: `telegram_bot/app/main.py`

- [ ] **Step 1: Add command handler and registration**

After `cmd_nutrition` (around line 40), add:

```python
async def cmd_body(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = " ".join(context.args) if context.args else "what's my current body composition"
    await _reply(update, f"body {text}")
```

In `main()` after the `CommandHandler("nutrition", cmd_nutrition)` line, add:

```python
    app.add_handler(CommandHandler("body", cmd_body))
```

- [ ] **Step 2: Manual smoke via bot logs**

Start the bot stack (`docker compose up telegram-bot`), send `/body` in Telegram, verify a reply arrives. No automated test for this (existing `/sleep` etc. are untested for the same reason).

- [ ] **Step 3: Commit**

```bash
git add telegram_bot/app/main.py
git commit -m "feat(telegram): /body command"
```

---

## Task 13: Smoke script

**Files:**
- Create: `scripts/smoke-body-agent.sh`

- [ ] **Step 1: Create the script**

```bash
cat > scripts/smoke-body-agent.sh <<'EOF'
#!/usr/bin/env bash
# End-to-end smoke test for agent-body against a running stack.
# Requires: docker compose up (postgres, qdrant, agent-body), .env with POSTGRES_* set.
set -euo pipefail

BODY_URL="${BODY_URL:-http://localhost:8004}"

echo "== AgentCard =="
curl -fsS "$BODY_URL/.well-known/agent.json" | python -c "import json,sys;c=json.load(sys.stdin);print(c['name'], c['protocol_version'], [s['id'] for s in c['skills']])"

echo
echo "== message/send get_latest_body =="
PAYLOAD=$(python - <<'PY'
import json, uuid
print(json.dumps({
  "jsonrpc": "2.0",
  "id": str(uuid.uuid4()),
  "method": "message/send",
  "params": {
    "message": {
      "role": "user",
      "parts": [{"kind": "text", "text": "what's my current weight"}],
      "messageId": str(uuid.uuid4()),
      "metadata": {"skillId": "get_latest_body"},
    }
  }
}))
PY
)

RESPONSE=$(curl -fsS -X POST "$BODY_URL/" -H 'Content-Type: application/json' -d "$PAYLOAD")
echo "$RESPONSE" | python -c "
import json, sys
r = json.load(sys.stdin)
result = r.get('result', {})
state = result.get('status', {}).get('state')
print('state =', state)
for art in result.get('artifacts') or []:
    for p in art.get('parts') or []:
        t = p.get('text') or (p.get('root') or {}).get('text')
        if t:
            print('artifact text:', t[:200])
assert state == 'completed', f'expected completed, got {state}'
"
echo "smoke passed"
EOF
chmod +x scripts/smoke-body-agent.sh
```

- [ ] **Step 2: Run it against the live stack**

```bash
./scripts/export-auth.sh
docker compose up -d postgres qdrant agent-body
./scripts/smoke-body-agent.sh
```
Expected: `state = completed` and non-empty artifact text (content depends on whether body data exists in DB; fallback "No body composition" text is acceptable).

- [ ] **Step 3: Commit**

```bash
git add scripts/smoke-body-agent.sh
git commit -m "chore(body): smoke script for agent-body"
```

---

## Task 14: End-to-end manual verification

- [ ] **Step 1: Bring up the full stack**

```bash
./scripts/export-auth.sh
docker compose up -d
docker compose ps
```
Expected: all services healthy; `agent-body` listed.

- [ ] **Step 2: Upload a ViHealth PDF via Telegram**

Send the PDF to the bot. Confirm it replies with a success message and that new metrics land in Postgres:

```bash
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "SELECT data->>'weight_kg', data->>'bmr_kcal', data->>'body_score' FROM health_logs WHERE type='body_composition' ORDER BY recorded_at DESC LIMIT 1;"
```
Expected: all three columns non-null (BMR and body_score are new).

- [ ] **Step 3: Ask the orchestrator in Telegram**

Send "сколько я вешу". Expected: reply contains the weight from the latest PDF.

Send "проанализируй историю веса". Expected: reply references nutrition/workout correlation.

- [ ] **Step 4: Run full test suite**

```bash
pytest -q
```
Expected: all tests pass.

- [ ] **Step 5: Final commit if any cleanup needed**

```bash
git status
# if nothing uncommitted, skip
```

---

## Notes / risks

- **Historical rows:** existing body rows have `agent='workout'`. `fetch_body_logs` filters by `type` only, so no migration is required. New rows will continue under whichever `agent` the mapper chooses — we deliberately do not change `map_body_composition`'s `agent` field in this plan to avoid touching unrelated logic. Follow-up option: flip to `agent='body'` in a separate cleanup PR.
- **No `briefing` skill on body:** the daily briefing path (`orchestrator/app/briefing.py`) does not currently loop through body. If you want body in the briefing, add a `briefing` skill mirroring the nutrition pattern in a follow-up — explicitly out of scope here.
- **Vision parser unchanged:** richer fields already extracted; only the downstream mapping changed. No new ANTHROPIC_API_KEY usage introduced.
