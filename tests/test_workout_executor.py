import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from a2a.types import Message, Part, TextPart, TaskState


def _ctx(text: str, skill_id: str | None = None, context_id: str = "ctx-1"):
    """Build a fake RequestContext the executor reads from."""
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
    from agents.workout.app.executor import WorkoutAgentExecutor

    ctx = _ctx("как тренировки", skill_id="analyze_workout")
    event_queue = MagicMock()
    event_queue.enqueue_event = AsyncMock()

    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(return_value=MagicMock(content="Хорошая неделя"))
    with patch("agents.workout.app.executor._LLM", fake_llm), \
         patch("agents.workout.app.executor.fetch_peer_artifacts", new=AsyncMock(return_value={})), \
         patch("agents.workout.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.workout.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.workout.app.executor.user_id_from_message",
               new=AsyncMock(return_value=uuid.UUID("00000000-0000-0000-0000-000000000000"))), \
         patch("agents.workout.app.executor.infer_skill_and_consults",
               new=AsyncMock(return_value=("analyze_workout", []))), \
         patch("agents.workout.app.executor.SKILL_PROMPTS", {"analyze_workout": AsyncMock(return_value="prompt")}):
        executor = WorkoutAgentExecutor()
        await executor.execute(ctx, event_queue)

    events = [c.args[0] for c in event_queue.enqueue_event.await_args_list]
    states = [getattr(e, "status", None) and e.status.state for e in events]
    assert TaskState.completed in [s for s in states if s is not None]


@pytest.mark.asyncio
async def test_executor_unknown_skill_fails_cleanly():
    from agents.workout.app.executor import WorkoutAgentExecutor

    ctx = _ctx("мусор", skill_id="nonexistent_skill")
    event_queue = MagicMock()
    event_queue.enqueue_event = AsyncMock()

    with patch("agents.workout.app.executor.SKILL_PROMPTS", {"analyze_workout": AsyncMock()}), \
         patch("agents.workout.app.executor.infer_skill_and_consults",
               new=AsyncMock(return_value=(None, []))):
        await WorkoutAgentExecutor().execute(ctx, event_queue)

    events = [c.args[0] for c in event_queue.enqueue_event.await_args_list]
    states = [getattr(e, "status", None) and e.status.state for e in events]
    assert TaskState.failed in [s for s in states if s is not None]


@pytest.mark.asyncio
async def test_executor_falls_back_to_intent_helper_when_no_skill_id():
    from agents.workout.app.executor import WorkoutAgentExecutor

    ctx = _ctx("как тренировки")  # no skill_id
    event_queue = MagicMock()
    event_queue.enqueue_event = AsyncMock()

    fake_prompt = AsyncMock(return_value="prompt")
    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(return_value=MagicMock(content="ok"))
    with patch("agents.workout.app.executor._LLM", fake_llm), \
         patch("agents.workout.app.executor.fetch_peer_artifacts", new=AsyncMock(return_value={})), \
         patch("agents.workout.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.workout.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.workout.app.executor.user_id_from_message",
               new=AsyncMock(return_value=uuid.UUID("00000000-0000-0000-0000-000000000000"))), \
         patch("agents.workout.app.executor.infer_skill_and_consults",
               new=AsyncMock(return_value=("analyze_workout", []))), \
         patch("agents.workout.app.executor.SKILL_PROMPTS", {"analyze_workout": fake_prompt}):
        executor = WorkoutAgentExecutor()
        await executor.execute(ctx, event_queue)

    assert fake_prompt.await_count == 1


@pytest.mark.asyncio
async def test_executor_subprocess_error_marks_failed():
    from agents.workout.app.executor import WorkoutAgentExecutor

    ctx = _ctx("broken", skill_id="analyze_workout")
    event_queue = MagicMock()
    event_queue.enqueue_event = AsyncMock()

    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(side_effect=RuntimeError("boom"))
    with patch("agents.workout.app.executor._LLM", fake_llm), \
         patch("agents.workout.app.executor.fetch_peer_artifacts", new=AsyncMock(return_value={})), \
         patch("agents.workout.app.executor.user_id_from_message",
               new=AsyncMock(return_value=uuid.UUID("00000000-0000-0000-0000-000000000000"))), \
         patch("agents.workout.app.executor.infer_skill_and_consults",
               new=AsyncMock(return_value=("analyze_workout", []))), \
         patch("agents.workout.app.executor.SKILL_PROMPTS", {"analyze_workout": AsyncMock(return_value="p")}):
        executor = WorkoutAgentExecutor()
        await executor.execute(ctx, event_queue)

    events = [c.args[0] for c in event_queue.enqueue_event.await_args_list]
    states = [getattr(e, "status", None) and e.status.state for e in events]
    assert TaskState.failed in [s for s in states if s is not None]


@pytest.mark.asyncio
async def test_executor_uses_intent_helper_consult_list():
    """Proves the executor uses the helper's output verbatim, including peer
    combinations the old hardcode never produced.  The old _decide_peers always
    returned ['sleep','nutrition'] for get_workout_recommendations; using
    ['recovery'] here means a regression that re-introduces the hardcode AFTER
    the helper call would fail this assertion."""
    from agents.workout.app.executor import WorkoutAgentExecutor

    ctx = _ctx("посоветуй тренировку с учётом сна и питания")  # no skillId
    event_queue = MagicMock()
    event_queue.enqueue_event = AsyncMock()

    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(return_value=MagicMock(content="ok"))
    fake_prompt = AsyncMock(return_value="prompt")
    fake_fetch = AsyncMock(return_value={"recovery": "R"})
    fake_intent = AsyncMock(return_value=("get_workout_recommendations", ["recovery"]))

    with patch("agents.workout.app.executor._LLM", fake_llm), \
         patch("agents.workout.app.executor.fetch_peer_artifacts", new=fake_fetch), \
         patch("agents.workout.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.workout.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.workout.app.executor.user_id_from_message",
               new=AsyncMock(return_value=uuid.UUID("00000000-0000-0000-0000-000000000000"))), \
         patch("agents.workout.app.executor.infer_skill_and_consults", new=fake_intent), \
         patch("agents.workout.app.executor.SKILL_PROMPTS", {"get_workout_recommendations": fake_prompt}):
        await WorkoutAgentExecutor().execute(ctx, event_queue)

    # fake_fetch called with needed={"recovery"} — a set the old hardcode could not produce
    args, kwargs = fake_fetch.await_args
    assert kwargs.get("needed") == {"recovery"}


@pytest.mark.asyncio
async def test_executor_metadata_focus_sources_passed_to_intent():
    """If orchestrator put focus_sources in metadata, helper sees it."""
    from agents.workout.app.executor import WorkoutAgentExecutor

    parts = [Part(root=TextPart(text="посоветуй тренировку"))]
    msg = Message(
        role="user", parts=parts, message_id="m1",
        metadata={"skillId": "get_workout_recommendations", "focus_sources": ["sleep"]},
    )
    ctx = MagicMock()
    ctx.message = msg
    ctx.context_id = "ctx-1"
    ctx.task_id = "task-1"
    ctx.current_task = None

    event_queue = MagicMock()
    event_queue.enqueue_event = AsyncMock()
    fake_intent = AsyncMock(return_value=("get_workout_recommendations", ["sleep"]))
    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(return_value=MagicMock(content="ok"))

    with patch("agents.workout.app.executor._LLM", fake_llm), \
         patch("agents.workout.app.executor.fetch_peer_artifacts", new=AsyncMock(return_value={})), \
         patch("agents.workout.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.workout.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.workout.app.executor.user_id_from_message",
               new=AsyncMock(return_value=uuid.UUID("00000000-0000-0000-0000-000000000000"))), \
         patch("agents.workout.app.executor.infer_skill_and_consults", new=fake_intent), \
         patch("agents.workout.app.executor.SKILL_PROMPTS", {"get_workout_recommendations": AsyncMock(return_value="p")}):
        await WorkoutAgentExecutor().execute(ctx, event_queue)

    _, kwargs = fake_intent.await_args
    md = kwargs["metadata"]
    assert md["focus_sources"] == ["sleep"]
    assert md["skillId"] == "get_workout_recommendations"
