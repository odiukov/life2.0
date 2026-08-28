"""Tests for shared.peer — A2A ClientFactory-based peer consultation."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

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


def _task_with_text(text: str) -> Task:
    artifact = Artifact(
        artifact_id="a1",
        name="peer_analysis",
        parts=[Part(root=TextPart(text=text))],
    )
    return Task(
        id="t1",
        context_id="c1",
        status=TaskStatus(state=TaskState.completed),
        artifacts=[artifact],
    )


def _make_client_yielding(items):
    """Build a mock client whose send_message returns an async generator."""
    async def _send_message(message):
        for it in items:
            yield it

    client = AsyncMock()
    # send_message must be a plain (non-awaitable) function returning an async iterator.
    client.send_message = lambda message: _send_message(message)
    return client


@pytest.mark.asyncio
async def test_fetch_peer_artifacts_returns_task_artifact_text():
    from shared import peer

    client = _make_client_yielding([(_task_with_text("workout summary"), None)])
    with patch("shared.peer.get_client", AsyncMock(return_value=client)):
        result = await peer.fetch_peer_artifacts(
            peer_agents={"workout": {"url": "http://agent-workout:8003"}},
            peer_task_names={"workout": "workout_summary"},
        )

    assert result == {"workout": "workout summary"}


@pytest.mark.asyncio
async def test_fetch_peer_artifacts_empty_needed_returns_empty():
    from shared import peer

    get_client_mock = AsyncMock()
    with patch("shared.peer.get_client", get_client_mock):
        result = await peer.fetch_peer_artifacts(
            peer_agents={"workout": {"url": "http://agent-workout:8003"}},
            peer_task_names={"workout": "workout_summary"},
            needed=set(),
        )

    assert result == {}
    get_client_mock.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_peer_artifacts_swallows_exception():
    from shared import peer

    with patch(
        "shared.peer.get_client",
        AsyncMock(side_effect=RuntimeError("boom")),
    ):
        result = await peer.fetch_peer_artifacts(
            peer_agents={"workout": {"url": "http://agent-workout:8003"}},
            peer_task_names={"workout": "workout_summary"},
        )

    assert result == {"workout": "(данные недоступны)"}


@pytest.mark.asyncio
async def test_call_peer_handles_plain_message_response():
    from shared import peer

    msg = Message(
        role=Role.agent,
        parts=[Part(root=TextPart(text="simple reply"))],
        message_id="m1",
    )
    client = _make_client_yielding([msg])
    with patch("shared.peer.get_client", AsyncMock(return_value=client)):
        text = await peer.call_peer("http://agent-x:8000", "some_skill")

    assert text == "simple reply"
