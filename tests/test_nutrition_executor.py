import uuid
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

    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(return_value=MagicMock(content="ok"))
    fake_intent = AsyncMock(return_value=("analyze_nutrition", []))
    with patch("agents.nutrition.app.executor._LLM", fake_llm), \
         patch("agents.nutrition.app.executor.fetch_peer_artifacts", new=AsyncMock(return_value={})), \
         patch("agents.nutrition.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.nutrition.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.nutrition.app.executor.user_id_from_message",
               new=AsyncMock(return_value=uuid.UUID("00000000-0000-0000-0000-000000000000"))), \
         patch("agents.nutrition.app.executor.infer_skill_and_consults", new=fake_intent), \
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

    fake_intent = AsyncMock(return_value=(None, []))
    with patch("agents.nutrition.app.executor.SKILL_PROMPTS", {"analyze_nutrition": AsyncMock()}), \
         patch("agents.nutrition.app.executor.infer_skill_and_consults", new=fake_intent):
        executor = NutritionAgentExecutor()
        await executor.execute(ctx, event_queue)

    events = [c.args[0] for c in event_queue.enqueue_event.await_args_list]
    states = [getattr(e, "status", None) and e.status.state for e in events]
    assert TaskState.failed in [s for s in states if s is not None]


@pytest.mark.asyncio
async def test_executor_falls_back_to_intent_helper_when_no_skill_id():
    from agents.nutrition.app.executor import NutritionAgentExecutor

    ctx = _ctx("как питание")
    event_queue = MagicMock()
    event_queue.enqueue_event = AsyncMock()

    fake_prompt = AsyncMock(return_value="prompt")
    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(return_value=MagicMock(content="ok"))
    fake_intent = AsyncMock(return_value=("analyze_nutrition", []))
    with patch("agents.nutrition.app.executor._LLM", fake_llm), \
         patch("agents.nutrition.app.executor.fetch_peer_artifacts", new=AsyncMock(return_value={})), \
         patch("agents.nutrition.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.nutrition.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.nutrition.app.executor.user_id_from_message",
               new=AsyncMock(return_value=uuid.UUID("00000000-0000-0000-0000-000000000000"))), \
         patch("agents.nutrition.app.executor.infer_skill_and_consults", new=fake_intent), \
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

    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(side_effect=RuntimeError("boom"))
    fake_intent = AsyncMock(return_value=("analyze_nutrition", []))
    with patch("agents.nutrition.app.executor._LLM", fake_llm), \
         patch("agents.nutrition.app.executor.fetch_peer_artifacts", new=AsyncMock(return_value={})), \
         patch("agents.nutrition.app.executor.user_id_from_message",
               new=AsyncMock(return_value=uuid.UUID("00000000-0000-0000-0000-000000000000"))), \
         patch("agents.nutrition.app.executor.infer_skill_and_consults", new=fake_intent), \
         patch("agents.nutrition.app.executor.SKILL_PROMPTS", {"analyze_nutrition": AsyncMock(return_value="p")}):
        executor = NutritionAgentExecutor()
        await executor.execute(ctx, event_queue)

    events = [c.args[0] for c in event_queue.enqueue_event.await_args_list]
    states = [getattr(e, "status", None) and e.status.state for e in events]
    assert TaskState.failed in [s for s in states if s is not None]


@pytest.mark.asyncio
async def test_nutrition_consult_list_propagates_to_fetch():
    """Old _decide_peers hardcoded {workout} for get_nutrition_recommendations.
    Use {sleep} (which old code could not produce for this skill) as a
    genuine regression guard."""
    from agents.nutrition.app.executor import NutritionAgentExecutor

    ctx = _ctx("посоветуй питание с учётом сна")  # no skillId
    event_queue = MagicMock(); event_queue.enqueue_event = AsyncMock()

    fake_intent = AsyncMock(return_value=("get_nutrition_recommendations", ["sleep"]))
    fake_fetch = AsyncMock(return_value={"sleep": "S"})
    fake_llm = MagicMock(); fake_llm.ainvoke = AsyncMock(return_value=MagicMock(content="ok"))
    import uuid as _uuid

    with patch("agents.nutrition.app.executor._LLM", fake_llm), \
         patch("agents.nutrition.app.executor.fetch_peer_artifacts", new=fake_fetch), \
         patch("agents.nutrition.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.nutrition.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.nutrition.app.executor.user_id_from_message",
               new=AsyncMock(return_value=_uuid.UUID("00000000-0000-0000-0000-000000000000"))), \
         patch("agents.nutrition.app.executor.infer_skill_and_consults", new=fake_intent), \
         patch("agents.nutrition.app.executor.SKILL_PROMPTS",
               {"get_nutrition_recommendations": AsyncMock(return_value="p")}):
        await NutritionAgentExecutor().execute(ctx, event_queue)

    _, kwargs = fake_fetch.await_args
    assert kwargs["needed"] == {"sleep"}


@pytest.mark.asyncio
async def test_nutrition_metadata_focus_sources_passed_to_intent():
    """Parity test: focus_sources flows through metadata to the helper."""
    from agents.nutrition.app.executor import NutritionAgentExecutor
    import uuid as _uuid

    parts = [Part(root=TextPart(text="посоветуй питание"))]
    msg = Message(
        role="user", parts=parts, message_id="m1",
        metadata={"skillId": "get_nutrition_recommendations", "focus_sources": ["workout"]},
    )
    ctx = MagicMock()
    ctx.message = msg
    ctx.context_id = "ctx-1"
    ctx.task_id = "task-1"
    ctx.current_task = None

    event_queue = MagicMock(); event_queue.enqueue_event = AsyncMock()
    fake_intent = AsyncMock(return_value=("get_nutrition_recommendations", ["workout"]))
    fake_llm = MagicMock(); fake_llm.ainvoke = AsyncMock(return_value=MagicMock(content="ok"))

    with patch("agents.nutrition.app.executor._LLM", fake_llm), \
         patch("agents.nutrition.app.executor.fetch_peer_artifacts", new=AsyncMock(return_value={})), \
         patch("agents.nutrition.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.nutrition.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.nutrition.app.executor.user_id_from_message",
               new=AsyncMock(return_value=_uuid.UUID("00000000-0000-0000-0000-000000000000"))), \
         patch("agents.nutrition.app.executor.infer_skill_and_consults", new=fake_intent), \
         patch("agents.nutrition.app.executor.SKILL_PROMPTS",
               {"get_nutrition_recommendations": AsyncMock(return_value="p")}):
        await NutritionAgentExecutor().execute(ctx, event_queue)

    _, kwargs = fake_intent.await_args
    md = kwargs["metadata"]
    assert md["focus_sources"] == ["workout"]
    assert md["skillId"] == "get_nutrition_recommendations"


@pytest.mark.asyncio
async def test_nutrition_set_body_profile_skips_peer_fetch_and_llm():
    """The direct skill (set_body_profile) must still bypass peer fetching and LLM prompting.
    Intent helper IS called (it short-circuits internally on metadata.skillId), but
    the executor goes straight to _execute_set_body_profile and returns."""
    from agents.nutrition.app.executor import NutritionAgentExecutor

    ctx = _ctx("set my height to 180", skill_id="set_body_profile")
    event_queue = MagicMock(); event_queue.enqueue_event = AsyncMock()
    import uuid as _uuid

    fake_intent = AsyncMock(return_value=("set_body_profile", []))
    fake_fetch = AsyncMock(return_value={})
    fake_llm = MagicMock(); fake_llm.ainvoke = AsyncMock()  # must NOT be called

    with patch("agents.nutrition.app.executor.infer_skill_and_consults", new=fake_intent), \
         patch("agents.nutrition.app.executor._LLM", fake_llm), \
         patch("agents.nutrition.app.executor.fetch_peer_artifacts", new=fake_fetch), \
         patch("agents.nutrition.app.executor._execute_set_body_profile",
               new=AsyncMock(return_value="profile saved")), \
         patch("agents.nutrition.app.executor.user_id_from_message",
               new=AsyncMock(return_value=_uuid.UUID("00000000-0000-0000-0000-000000000000"))), \
         patch("agents.nutrition.app.executor.insert_task_record", new=AsyncMock()):
        await NutritionAgentExecutor().execute(ctx, event_queue)

    # intent helper was called (cheap — short-circuits internally on metadata.skillId)
    assert fake_intent.await_count == 1
    # but no peer fetch and no LLM prompt — direct path
    fake_fetch.assert_not_awaited()
    fake_llm.ainvoke.assert_not_awaited()
