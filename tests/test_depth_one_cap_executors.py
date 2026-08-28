"""Each peer-consuming executor must skip its own fetch_peer_artifacts when
called as a peer (metadata.is_peer_call=True). Today this is masked because
non-mandatory skills get an empty consult list, but a future addition to
MANDATORY_CONSULTS would regress into depth-2 fan-out without this guard."""
from __future__ import annotations

import types
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


PEER_CONSUMING_AGENTS = ["sleep", "workout", "nutrition", "body", "mood", "recovery"]
# habits and medication only fan out for analyze_*, but their executor branches
# are wrapped in if-skill guards already; the helper still applies in principle
# but covering them adds branch noise without behavior change.


class _FakeMessage:
    def __init__(self, metadata):
        self.parts = []
        self.metadata = metadata
        self.message_id = "test-msg"


class _FakeCtx:
    def __init__(self, metadata):
        self.message = _FakeMessage(metadata)
        self.task_id = "t1"
        self.context_id = "c1"


@pytest.mark.asyncio
@pytest.mark.parametrize("agent", PEER_CONSUMING_AGENTS)
async def test_executor_skips_peer_fetch_when_is_peer_call_true(agent):
    """When metadata.is_peer_call is True, fetch_peer_artifacts must NOT be called.
    The agent should still produce a response, just without consulting peers."""
    mod = __import__(f"agents.{agent}.app.executor", fromlist=["*"])
    skills_mod = __import__(f"agents.{agent}.app.skills", fromlist=["SKILL_PROMPTS"])
    valid_skills = list(skills_mod.SKILL_PROMPTS.keys())
    # Pick a peer-consuming analytical skill if present, else the first skill.
    skill_pref = [
        "analyze_sleep", "analyze_workout", "analyze_nutrition",
        "analyze_body_trend", "analyze_mood", "analyze_recovery_trend",
        "get_recommendations", "get_workout_recommendations",
        "get_nutrition_recommendations", "get_sleep_recommendations",
        "get_mood_recommendations",
    ]
    skill_id = next((s for s in skill_pref if s in valid_skills), valid_skills[0])

    # Fake LLM: returns whatever response is asked for
    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(return_value=types.SimpleNamespace(content="ok"))

    # The infer router won't be called because metadata.skillId short-circuits.
    metadata = {"skillId": skill_id, "is_peer_call": True}
    ctx = _FakeCtx(metadata)

    fetch_called = False

    async def _spy_fetch(*args, **kwargs):
        nonlocal fetch_called
        fetch_called = True
        return {}

    async def _no_user(*_a, **_kw):
        return uuid.uuid4()

    async def _no_op(*_a, **_kw):
        return None

    # Patch the LLM, the user_id resolver, db writes, and event emission.
    queue = MagicMock()
    queue.enqueue_event = AsyncMock()

    with patch.object(mod, "_get_llm", return_value=fake_llm), \
         patch.object(mod, "fetch_peer_artifacts", _spy_fetch), \
         patch.object(mod, "user_id_from_message", _no_user), \
         patch.object(mod, "insert_task_record", _no_op), \
         patch.object(mod, "upsert_memory", _no_op):
        # Also stub the prompt builder so it doesn't hit DB.
        async def _stub_prompt(message, params):
            return "stub prompt"
        with patch.dict(skills_mod.SKILL_PROMPTS, {skill_id: _stub_prompt}):
            executor_cls = next(
                v for k, v in mod.__dict__.items()
                if isinstance(v, type)
                and k.endswith("AgentExecutor")
                and k != "AgentExecutor"
            )
            executor = executor_cls()
            await executor.execute(ctx, queue)

    assert not fetch_called, (
        f"{agent}: fetch_peer_artifacts was called even though metadata.is_peer_call=True"
    )
