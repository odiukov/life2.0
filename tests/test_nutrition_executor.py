import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from a2a.types import Message, Part, TextPart, TaskState


def _ctx(text: str, skill_id: str | None = None, context_id: str = "ctx-1"):
    parts = [Part(root=TextPart(text=text))]
    metadata = {"skillId": skill_id} if skill_id else None
    msg = Message(role="user", parts=parts, message_id="m1", metadata=metadata)
    ctx = MagicMock()
    ctx.message = msg
    ctx.context_id = context_id
    ctx.task_id = "task-1"
    ctx.current_task = None
    return ctx


@pytest.mark.asyncio
async def test_executor_happy_path_uses_skill_id_and_emits_completed():
    from agents.nutrition.app.executor import NutritionAgentExecutor

    ctx = _ctx("как питание", skill_id="analyze_nutrition")
    event_queue = MagicMock()
    event_queue.enqueue_event = AsyncMock()

    with patch("agents.nutrition.app.executor.run_claude", return_value="ok"), \
         patch("agents.nutrition.app.executor.fetch_peer_artifacts", new=AsyncMock(return_value={})), \
         patch("agents.nutrition.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.nutrition.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.nutrition.app.executor.SKILL_PROMPTS", {"analyze_nutrition": AsyncMock(return_value="prompt")}):
        executor = NutritionAgentExecutor()
        await executor.execute(ctx, event_queue)

    events = [c.args[0] for c in event_queue.enqueue_event.await_args_list]
    states = [getattr(e, "status", None) and e.status.state for e in events]
    assert TaskState.completed in [s for s in states if s is not None]


@pytest.mark.asyncio
async def test_executor_unknown_skill_fails_cleanly():
    from agents.nutrition.app.executor import NutritionAgentExecutor

    ctx = _ctx("мусор", skill_id="nonexistent_skill")
    event_queue = MagicMock()
    event_queue.enqueue_event = AsyncMock()

    with patch("agents.nutrition.app.executor.SKILL_PROMPTS", {"analyze_nutrition": AsyncMock()}), \
         patch("agents.nutrition.app.executor._infer_skill_via_llm", new=AsyncMock(return_value=None)):
        executor = NutritionAgentExecutor()
        await executor.execute(ctx, event_queue)

    events = [c.args[0] for c in event_queue.enqueue_event.await_args_list]
    states = [getattr(e, "status", None) and e.status.state for e in events]
    assert TaskState.failed in [s for s in states if s is not None]


@pytest.mark.asyncio
async def test_executor_falls_back_to_llm_infer_when_no_skill_id():
    from agents.nutrition.app.executor import NutritionAgentExecutor

    ctx = _ctx("как питание")
    event_queue = MagicMock()
    event_queue.enqueue_event = AsyncMock()

    fake_prompt = AsyncMock(return_value="prompt")
    with patch("agents.nutrition.app.executor.run_claude", return_value="ok"), \
         patch("agents.nutrition.app.executor.fetch_peer_artifacts", new=AsyncMock(return_value={})), \
         patch("agents.nutrition.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.nutrition.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.nutrition.app.executor._infer_skill_via_llm", new=AsyncMock(return_value="analyze_nutrition")), \
         patch("agents.nutrition.app.executor.SKILL_PROMPTS", {"analyze_nutrition": fake_prompt}):
        executor = NutritionAgentExecutor()
        await executor.execute(ctx, event_queue)

    assert fake_prompt.await_count == 1


@pytest.mark.asyncio
async def test_executor_subprocess_error_marks_failed():
    from agents.nutrition.app.executor import NutritionAgentExecutor

    ctx = _ctx("broken", skill_id="analyze_nutrition")
    event_queue = MagicMock()
    event_queue.enqueue_event = AsyncMock()

    with patch("agents.nutrition.app.executor.run_claude", side_effect=RuntimeError("boom")), \
         patch("agents.nutrition.app.executor.fetch_peer_artifacts", new=AsyncMock(return_value={})), \
         patch("agents.nutrition.app.executor.SKILL_PROMPTS", {"analyze_nutrition": AsyncMock(return_value="p")}):
        executor = NutritionAgentExecutor()
        await executor.execute(ctx, event_queue)

    events = [c.args[0] for c in event_queue.enqueue_event.await_args_list]
    states = [getattr(e, "status", None) and e.status.state for e in events]
    assert TaskState.failed in [s for s in states if s is not None]


def test_decide_peers_log_meal_returns_empty():
    from agents.nutrition.app.executor import _decide_peers

    assert _decide_peers("log_meal", "anything with тренировк") == set()


def test_decide_peers_get_recommendations_always_includes_workout():
    from agents.nutrition.app.executor import _decide_peers

    assert _decide_peers("get_nutrition_recommendations", "abc") == {"workout"}


def test_decide_peers_analyze_nutrition_uses_keywords():
    from agents.nutrition.app.executor import _decide_peers

    assert _decide_peers("analyze_nutrition", "как моя тренировка") == {"workout"}
    assert _decide_peers("analyze_nutrition", "как мой сон") == {"sleep"}
    assert _decide_peers("analyze_nutrition", "сон и тренировка") == {"sleep", "workout"}
    assert _decide_peers("analyze_nutrition", "привет") == set()
