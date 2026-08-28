"""Tests for RecoveryAgentExecutor dispatch."""
import pytest
from types import SimpleNamespace
from uuid import UUID
from unittest.mock import AsyncMock, patch
from a2a.types import Message, Part, Role, TaskState, TextPart


USER = UUID("00000000-0000-0000-0000-000000000001")


class _patch_owner:
    """Stub fetch_peer_artifacts (executor calls it on every non-peer-call
    path). user_id is now resolved strictly from Message.metadata, which
    _Ctx already populates."""
    def __enter__(self):
        self._patches = [
            patch("agents.recovery.app.executor.fetch_peer_artifacts",
                  new=AsyncMock(return_value={})),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self._patches:
            p.stop()


class _Ctx:
    def __init__(self, text: str, skill: str | None = None, params: dict | None = None):
        self.task_id = "t1"
        self.context_id = "c1"
        meta: dict = {"user_id": "00000000-0000-0000-0000-000000000001"}
        if skill:
            meta["skillId"] = skill
        if params is not None:
            meta["params"] = params
        self.message = Message(
            role=Role.user,
            parts=[Part(root=TextPart(text=text))],
            message_id="m1",
            metadata=meta or None,
        )


class _Queue:
    def __init__(self):
        self.events = []

    async def enqueue_event(self, evt):
        self.events.append(evt)


def _fake_llm(content: str):
    return SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content=content)))


_FAKE_METRICS = {
    "2026-04-17": {"hrv": 45, "rhr": 58, "stress": 34, "bb_min": 25, "bb_max": 85, "sleep_score": 82},
    "2026-04-16": {"hrv": 43, "rhr": 60, "stress": 40, "bb_min": 20, "bb_max": 80, "sleep_score": 78},
    "2026-04-15": {"hrv": 44, "rhr": 59, "stress": 38, "bb_min": 22, "bb_max": 82, "sleep_score": 80},
}


@pytest.mark.asyncio
async def test_executor_get_readiness_emits_completed_with_llm_text():
    from agents.recovery.app.executor import RecoveryAgentExecutor

    with _patch_owner(), \
         patch("agents.recovery.app.executor._get_llm",
               return_value=_fake_llm("You are recovered.")), \
         patch("agents.recovery.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.recovery.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.recovery.app.prompt.fetch_recovery_metrics",
               new=AsyncMock(return_value=_FAKE_METRICS)):
        q = _Queue()
        await RecoveryAgentExecutor().execute(
            _Ctx("am I recovered", skill="get_readiness"), q,
        )
    states = [e.status.state for e in q.events if hasattr(e, "status")]
    assert TaskState.completed in states
    text_artifacts = [e.artifact.parts[0].root.text for e in q.events
                      if hasattr(e, "artifact") and e.artifact.name == "analysis"]
    assert any("recovered" in t.lower() for t in text_artifacts)


@pytest.mark.asyncio
async def test_executor_analyze_trend_emits_completed():
    from agents.recovery.app.executor import RecoveryAgentExecutor

    with _patch_owner(), \
         patch("agents.recovery.app.executor._get_llm",
               return_value=_fake_llm("HRV trending up.")), \
         patch("agents.recovery.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.recovery.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.recovery.app.prompt.fetch_recovery_metrics",
               new=AsyncMock(return_value=_FAKE_METRICS)):
        q = _Queue()
        await RecoveryAgentExecutor().execute(
            _Ctx("trend this week", skill="analyze_recovery_trend"), q,
        )
    states = [e.status.state for e in q.events if hasattr(e, "status")]
    assert TaskState.completed in states


@pytest.mark.asyncio
async def test_executor_unknown_skill_fails():
    from agents.recovery.app.executor import RecoveryAgentExecutor

    with patch("agents.recovery.app.executor._get_llm", return_value=_fake_llm("")):
        q = _Queue()
        await RecoveryAgentExecutor().execute(_Ctx("what"), q)
    failed = [e for e in q.events if hasattr(e, "status") and e.status.state == TaskState.failed]
    assert failed
