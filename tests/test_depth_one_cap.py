"""Depth-1 cap on peer-consult fan-out. call_peer must propagate
is_peer_call=True so the receiving agent's executor knows it's a peer call
and skips its own peer-consult step."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from shared import peer as peer_mod


@pytest.mark.asyncio
async def test_call_peer_propagates_is_peer_call_true_in_metadata():
    captured: dict = {}

    async def _send_message(message):
        captured["metadata"] = dict(message.metadata or {})
        return
        yield  # async generator

    client = AsyncMock()
    client.send_message = lambda message: _send_message(message)

    with patch("shared.peer.get_client", AsyncMock(return_value=client)):
        await peer_mod.call_peer(
            "http://x:1/", "analyze_workout",
            user_id="u1", for_date="2026-04-30",
        )

    assert captured["metadata"]["is_peer_call"] is True


def test_is_peer_call_from_metadata_returns_true():
    assert peer_mod.is_peer_call_from_metadata({"is_peer_call": True}) is True


def test_is_peer_call_from_metadata_returns_false_when_absent():
    assert peer_mod.is_peer_call_from_metadata({}) is False
    assert peer_mod.is_peer_call_from_metadata(None) is False


def test_is_peer_call_from_metadata_returns_false_for_falsy_values():
    assert peer_mod.is_peer_call_from_metadata({"is_peer_call": False}) is False
    assert peer_mod.is_peer_call_from_metadata({"is_peer_call": "true"}) is False  # strict
