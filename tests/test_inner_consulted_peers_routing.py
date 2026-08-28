"""Verify _call_agent_with_artifact extracts the consulted_peers artifact and
that _run_peer_tool propagates it onto the ToolCall, so /chat/stream can show
the 'via X' chips for sleep-agent's internal peer fan-out."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from a2a.types import (  # noqa: E402
    Artifact,
    DataPart,
    Part,
    Task,
    TaskState,
    TaskStatus,
    TextPart,
)


def _task(text: str, peers: list[str] | None) -> Task:
    artifacts = [
        Artifact(
            artifact_id="a1",
            name="analysis",
            parts=[Part(root=TextPart(text=text))],
        ),
    ]
    if peers is not None:
        artifacts.append(
            Artifact(
                artifact_id="a2",
                name="consulted_peers",
                parts=[Part(root=DataPart(data={"peers": peers}))],
            )
        )
    return Task(
        id="t1",
        context_id="c1",
        status=TaskStatus(state=TaskState.completed),
        artifacts=artifacts,
    )


def _make_client(task: Task):
    async def _send_message(_msg):
        yield (task, None)

    client = AsyncMock()
    client.send_message = lambda message: _send_message(message)
    return client


def test_extract_consulted_peers_returns_list():
    from orchestrator.app.health_agent import _extract_consulted_peers_from_task
    out = _extract_consulted_peers_from_task(
        _task("hello", ["nutrition", "workout"])
    )
    assert out == ["nutrition", "workout"]


def test_extract_consulted_peers_returns_none_when_artifact_absent():
    """Older agents (no consulted_peers artifact) → None, not []."""
    from orchestrator.app.health_agent import _extract_consulted_peers_from_task
    assert _extract_consulted_peers_from_task(_task("hi", None)) is None


def test_extract_consulted_peers_empty_list_round_trip():
    from orchestrator.app.health_agent import _extract_consulted_peers_from_task
    assert _extract_consulted_peers_from_task(_task("hi", [])) == []


@pytest.mark.asyncio
async def test_call_agent_with_artifact_returns_consulted_peers():
    from orchestrator.app import health_agent

    client = _make_client(_task("ok", ["nutrition", "workout"]))
    with patch.object(health_agent, "_resolve_url", return_value="http://x:1/"), \
         patch.object(health_agent, "get_client", AsyncMock(return_value=client)):
        text, log_entry, peers = await health_agent._call_agent_with_artifact(
            "sleep", "msg", "analyze_sleep",
        )
    assert text == "ok"
    assert log_entry is None
    assert peers == ["nutrition", "workout"]


@pytest.mark.asyncio
async def test_call_agent_with_artifact_returns_none_when_artifact_absent():
    from orchestrator.app import health_agent

    client = _make_client(_task("ok", None))
    with patch.object(health_agent, "_resolve_url", return_value="http://x:1/"), \
         patch.object(health_agent, "get_client", AsyncMock(return_value=client)):
        _text, _le, peers = await health_agent._call_agent_with_artifact(
            "sleep", "msg", "analyze_sleep",
        )
    assert peers is None
