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
    from agents.sleep.app.executor import SleepAgentExecutor

    ctx = _ctx("как спалось", skill_id="analyze_sleep")
    event_queue = MagicMock()
    event_queue.enqueue_event = AsyncMock()

    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(return_value=MagicMock(content="Спал отлично"))
    with patch("agents.sleep.app.executor._LLM", fake_llm), \
         patch("agents.sleep.app.executor.fetch_peer_artifacts", new=AsyncMock(return_value={})), \
         patch("agents.sleep.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.sleep.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.sleep.app.executor.user_id_from_message",
               new=AsyncMock(return_value=uuid.UUID("00000000-0000-0000-0000-000000000000"))), \
         patch("agents.sleep.app.executor.infer_skill_and_consults",
               new=AsyncMock(return_value=("analyze_sleep", []))), \
         patch("agents.sleep.app.executor.SKILL_PROMPTS", {"analyze_sleep": AsyncMock(return_value="prompt")}):
        executor = SleepAgentExecutor()
        await executor.execute(ctx, event_queue)

    events = [c.args[0] for c in event_queue.enqueue_event.await_args_list]
    states = [getattr(e, "status", None) and e.status.state for e in events]
    assert TaskState.completed in [s for s in states if s is not None]


@pytest.mark.asyncio
async def test_executor_unknown_skill_fails_cleanly():
    from agents.sleep.app.executor import SleepAgentExecutor

    ctx = _ctx("мусор", skill_id="nonexistent_skill")
    event_queue = MagicMock()
    event_queue.enqueue_event = AsyncMock()

    with patch("agents.sleep.app.executor.SKILL_PROMPTS", {"analyze_sleep": AsyncMock()}), \
         patch("agents.sleep.app.executor.infer_skill_and_consults",
               new=AsyncMock(return_value=(None, []))):
        executor = SleepAgentExecutor()
        await executor.execute(ctx, event_queue)

    events = [c.args[0] for c in event_queue.enqueue_event.await_args_list]
    states = [getattr(e, "status", None) and e.status.state for e in events]
    assert TaskState.failed in [s for s in states if s is not None]


@pytest.mark.asyncio
async def test_executor_falls_back_to_intent_helper_when_no_skill_id():
    from agents.sleep.app.executor import SleepAgentExecutor

    ctx = _ctx("как спалось")  # no skill_id
    event_queue = MagicMock()
    event_queue.enqueue_event = AsyncMock()

    fake_prompt = AsyncMock(return_value="prompt")
    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(return_value=MagicMock(content="ok"))
    with patch("agents.sleep.app.executor._LLM", fake_llm), \
         patch("agents.sleep.app.executor.fetch_peer_artifacts", new=AsyncMock(return_value={})), \
         patch("agents.sleep.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.sleep.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.sleep.app.executor.user_id_from_message",
               new=AsyncMock(return_value=uuid.UUID("00000000-0000-0000-0000-000000000000"))), \
         patch("agents.sleep.app.executor.infer_skill_and_consults",
               new=AsyncMock(return_value=("analyze_sleep", []))), \
         patch("agents.sleep.app.executor.SKILL_PROMPTS", {"analyze_sleep": fake_prompt}):
        executor = SleepAgentExecutor()
        await executor.execute(ctx, event_queue)

    assert fake_prompt.await_count == 1


@pytest.mark.asyncio
async def test_executor_subprocess_error_marks_failed():
    from agents.sleep.app.executor import SleepAgentExecutor

    ctx = _ctx("broken", skill_id="analyze_sleep")
    event_queue = MagicMock()
    event_queue.enqueue_event = AsyncMock()

    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(side_effect=RuntimeError("boom"))
    with patch("agents.sleep.app.executor._LLM", fake_llm), \
         patch("agents.sleep.app.executor.fetch_peer_artifacts", new=AsyncMock(return_value={})), \
         patch("agents.sleep.app.executor.user_id_from_message",
               new=AsyncMock(return_value=uuid.UUID("00000000-0000-0000-0000-000000000000"))), \
         patch("agents.sleep.app.executor.infer_skill_and_consults",
               new=AsyncMock(return_value=("analyze_sleep", []))), \
         patch("agents.sleep.app.executor.SKILL_PROMPTS", {"analyze_sleep": AsyncMock(return_value="p")}):
        executor = SleepAgentExecutor()
        await executor.execute(ctx, event_queue)

    events = [c.args[0] for c in event_queue.enqueue_event.await_args_list]
    states = [getattr(e, "status", None) and e.status.state for e in events]
    assert TaskState.failed in [s for s in states if s is not None]


@pytest.mark.asyncio
async def test_sleep_executor_passes_consult_to_fetch():
    from agents.sleep.app.executor import SleepAgentExecutor

    ctx = _ctx("анализируй сон с учётом тренировок")  # no skillId
    event_queue = MagicMock()
    event_queue.enqueue_event = AsyncMock()

    fake_intent = AsyncMock(return_value=("analyze_sleep", ["workout"]))
    fake_fetch = AsyncMock(return_value={"workout": "W"})
    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(return_value=MagicMock(content="ok"))

    with patch("agents.sleep.app.executor._LLM", fake_llm), \
         patch("agents.sleep.app.executor.fetch_peer_artifacts", new=fake_fetch), \
         patch("agents.sleep.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.sleep.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.sleep.app.executor.user_id_from_message",
               new=AsyncMock(return_value=uuid.UUID("00000000-0000-0000-0000-000000000000"))), \
         patch("agents.sleep.app.executor.infer_skill_and_consults", new=fake_intent), \
         patch("agents.sleep.app.executor.SKILL_PROMPTS", {"analyze_sleep": AsyncMock(return_value="p")}):
        await SleepAgentExecutor().execute(ctx, event_queue)

    _, kwargs = fake_fetch.await_args
    assert kwargs["needed"] == {"workout"}


@pytest.mark.asyncio
async def test_sleep_executor_get_recommendations_no_longer_hardcodes_workout():
    """Old _decide_peers hardcoded {workout} for get_sleep_recommendations.
    Verify the executor uses the helper's output even when it differs."""
    from agents.sleep.app.executor import SleepAgentExecutor

    ctx = _ctx("посоветуй сон")  # no skillId
    event_queue = MagicMock()
    event_queue.enqueue_event = AsyncMock()

    # helper returns nutrition-only — old hardcode would have returned {workout}
    fake_intent = AsyncMock(return_value=("get_sleep_recommendations", ["nutrition"]))
    fake_fetch = AsyncMock(return_value={"nutrition": "N"})
    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(return_value=MagicMock(content="ok"))

    with patch("agents.sleep.app.executor._LLM", fake_llm), \
         patch("agents.sleep.app.executor.fetch_peer_artifacts", new=fake_fetch), \
         patch("agents.sleep.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.sleep.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.sleep.app.executor.user_id_from_message",
               new=AsyncMock(return_value=uuid.UUID("00000000-0000-0000-0000-000000000000"))), \
         patch("agents.sleep.app.executor.infer_skill_and_consults", new=fake_intent), \
         patch("agents.sleep.app.executor.SKILL_PROMPTS", {"get_sleep_recommendations": AsyncMock(return_value="p")}):
        await SleepAgentExecutor().execute(ctx, event_queue)

    _, kwargs = fake_fetch.await_args
    assert kwargs["needed"] == {"nutrition"}
