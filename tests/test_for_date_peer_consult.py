"""Verify sleep agent passes `for_date=yesterday` when consulting peers, and
that nutrition/workout prompts honor the param to scope to that calendar day."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest


# ----------------------------- shared.peer ---------------------------------


@pytest.mark.asyncio
async def test_call_peer_propagates_for_date_in_metadata():
    from shared import peer

    captured: dict = {}

    async def _send_message(message):
        captured["metadata"] = dict(message.metadata or {})
        captured["text"] = message.parts[0].root.text
        return
        yield  # make it an async generator

    client = AsyncMock()
    client.send_message = lambda message: _send_message(message)

    with patch("shared.peer.get_client", AsyncMock(return_value=client)):
        await peer.call_peer(
            "http://x:1/", "analyze_nutrition",
            user_id="u1", for_date="2026-04-30",
        )

    assert captured["metadata"]["for_date"] == "2026-04-30"
    assert captured["metadata"]["skillId"] == "analyze_nutrition"
    assert captured["metadata"]["user_id"] == "u1"
    assert "2026-04-30" in captured["text"]


@pytest.mark.asyncio
async def test_call_peer_omits_for_date_when_absent():
    from shared import peer

    captured: dict = {}

    async def _send_message(message):
        captured["metadata"] = dict(message.metadata or {})
        return
        yield

    client = AsyncMock()
    client.send_message = lambda message: _send_message(message)

    with patch("shared.peer.get_client", AsyncMock(return_value=client)):
        await peer.call_peer("http://x:1/", "analyze_nutrition")

    assert "for_date" not in captured["metadata"]


@pytest.mark.asyncio
async def test_fetch_peer_artifacts_forwards_for_date():
    from shared import peer

    captured: list[dict] = []

    async def _fake_call_peer(url, skill, *, user_id=None, for_date=None, **_kw):
        captured.append({"url": url, "skill": skill, "for_date": for_date})
        return "stub"

    with patch("shared.peer.call_peer", _fake_call_peer):
        await peer.fetch_peer_artifacts(
            peer_agents={"workout": {"url": "http://w:1/"}, "nutrition": {"url": "http://n:1/"}},
            peer_task_names={"workout": "analyze_workout", "nutrition": "analyze_nutrition"},
            for_date="2026-04-30",
        )

    assert len(captured) == 2
    assert all(c["for_date"] == "2026-04-30" for c in captured)


# ----------------------------- nutrition prompt -----------------------------


@pytest.mark.asyncio
async def test_nutrition_prompt_uses_for_date_when_provided():
    """When for_date is passed, "Today (...)" header must read the target day."""
    from agents.nutrition.app import prompt as nut_prompt

    target = (datetime.now(timezone.utc).date() - timedelta(days=1))

    async def _zero_logs(*_a, **_k):
        return []

    async def _no_body(*_a, **_k):
        return []

    async def _no_profile(*_a, **_k):
        return None

    async def _no_memories(*_a, **_k):
        return []

    with patch.object(nut_prompt, "fetch_recent_logs", _zero_logs), \
         patch.object(nut_prompt, "fetch_body_logs", _no_body), \
         patch.object(nut_prompt, "get_body_profile", _no_profile), \
         patch.object(nut_prompt, "search_memories", _no_memories):
        text = await nut_prompt.build_nutrition_prompt(
            "analyze_nutrition",
            {"user_id": "00000000-0000-0000-0000-000000000001",
             "for_date": target.isoformat()},
        )

    assert f"Day ({target.isoformat()})" in text
    # And no "Today (YYYY-MM-DD)" header for current UTC date
    today = datetime.now(timezone.utc).date()
    assert f"Today ({today.isoformat()})" not in text


@pytest.mark.asyncio
async def test_nutrition_prompt_defaults_to_today_without_for_date():
    from agents.nutrition.app import prompt as nut_prompt

    today = datetime.now(timezone.utc).date()

    async def _zero(*_a, **_k):
        return []

    async def _none(*_a, **_k):
        return None

    with patch.object(nut_prompt, "fetch_recent_logs", _zero), \
         patch.object(nut_prompt, "fetch_body_logs", _zero), \
         patch.object(nut_prompt, "get_body_profile", _none), \
         patch.object(nut_prompt, "search_memories", _zero):
        text = await nut_prompt.build_nutrition_prompt(
            "analyze_nutrition",
            {"user_id": "00000000-0000-0000-0000-000000000001"},
        )

    assert f"Today ({today.isoformat()})" in text


# ----------------------------- workout prompt -----------------------------


@pytest.mark.asyncio
async def test_workout_prompt_surfaces_focus_date_when_provided():
    from agents.workout.app import prompt as w_prompt

    async def _zero(*_a, **_k):
        return []

    with patch.object(w_prompt, "fetch_recent_logs", _zero), \
         patch.object(w_prompt, "fetch_body_logs", _zero), \
         patch.object(w_prompt, "search_memories", _zero):
        text = await w_prompt.build_workout_prompt(
            "analyze_workout",
            {"user_id": "00000000-0000-0000-0000-000000000001",
             "for_date": "2026-04-30"},
        )

    assert "Peer-consult focus date: 2026-04-30" in text


@pytest.mark.asyncio
async def test_workout_prompt_omits_focus_date_section_when_absent():
    from agents.workout.app import prompt as w_prompt

    async def _zero(*_a, **_k):
        return []

    with patch.object(w_prompt, "fetch_recent_logs", _zero), \
         patch.object(w_prompt, "fetch_body_logs", _zero), \
         patch.object(w_prompt, "search_memories", _zero):
        text = await w_prompt.build_workout_prompt(
            "analyze_workout",
            {"user_id": "00000000-0000-0000-0000-000000000001"},
        )

    assert "Peer-consult focus date" not in text
