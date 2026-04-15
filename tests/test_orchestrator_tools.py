"""Tests for orchestrator per-agent LangGraph tools."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from a2a.types import (
    Artifact,
    Message,
    Part,
    Role,
    Task,
    TaskState,
    TaskStatus,
    TextPart,
)

from orchestrator.app.health_agent import ask_sleep_agent


def _make_task(text: str) -> Task:
    return Task(
        id="t1",
        context_id="c1",
        status=TaskStatus(state=TaskState.completed),
        artifacts=[
            Artifact(
                artifact_id="a1",
                name="analysis",
                parts=[Part(root=TextPart(text=text))],
            )
        ],
    )


class _FakeClient:
    def __init__(self, task: Task) -> None:
        self._task = task
        self.sent: list[Message] = []

    def send_message(self, message: Message):
        # Sync callable returning an async generator — matches the SDK shape.
        self.sent.append(message)

        async def _gen():
            yield (self._task, None)

        return _gen()


def _tool_call(args: dict, tc_id: str = "tc") -> dict:
    return {
        "name": "ask_sleep_agent",
        "type": "tool_call",
        "id": tc_id,
        "args": {**args, "state": {"messages": [], "toolCalls": []}},
    }


@pytest.mark.asyncio
async def test_ask_sleep_agent_returns_artifact_and_passes_skill():
    fake = _FakeClient(_make_task("sleep summary"))

    async def fake_get_client(url: str):
        return fake

    with patch(
        "orchestrator.app.health_agent.get_client", side_effect=fake_get_client
    ), patch(
        "orchestrator.app.health_agent._resolve_url",
        return_value="http://sleep-agent:8080",
    ), patch(
        "orchestrator.app.health_agent.copilotkit_emit_state",
    ):
        cmd = await ask_sleep_agent.ainvoke(
            _tool_call({"message": "how did I sleep?", "skill": "analyze_sleep"})
        )

    tool_msg = cmd.update["messages"][0]
    assert tool_msg.content == "sleep summary"
    assert len(fake.sent) == 1
    sent = fake.sent[0]
    assert sent.role == Role.user
    assert sent.metadata == {"skillId": "analyze_sleep"}
    # Verify message text propagated
    root = getattr(sent.parts[0], "root", sent.parts[0])
    assert getattr(root, "text", "") == "how did I sleep?"


@pytest.mark.asyncio
async def test_ask_sleep_agent_returns_unavailable_when_url_missing():
    with patch(
        "orchestrator.app.health_agent._resolve_url", return_value=None
    ), patch(
        "orchestrator.app.health_agent.copilotkit_emit_state",
    ):
        cmd = await ask_sleep_agent.ainvoke(
            _tool_call({"message": "hi", "skill": "analyze_sleep"})
        )
    assert "unavailable" in cmd.update["messages"][0].content.lower()
