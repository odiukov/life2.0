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
