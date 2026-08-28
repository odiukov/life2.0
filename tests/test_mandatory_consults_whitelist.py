"""Mandatory-consult whitelist: certain skills must always trigger specific
peer consults regardless of LLM output, because the agent semantically needs
that grounding (e.g. workout recommendations need recovery + sleep)."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.intent import infer_skill_and_consults


@pytest.mark.asyncio
async def test_workout_recommendations_always_consult_recovery_and_sleep():
    """LLM returns empty consult — whitelist must inject recovery + sleep."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=SimpleNamespace(
        content=json.dumps({
            "skill": "get_workout_recommendations",
            "consult": [],
        })
    ))
    skill_id, consult = await infer_skill_and_consults(
        message="посоветуй тренировку",
        skills=["log_workout", "analyze_workout", "get_workout_recommendations"],
        candidate_peers=["recovery", "sleep", "nutrition", "body"],
        metadata=None,
        llm=llm,
    )
    assert skill_id == "get_workout_recommendations"
    assert "recovery" in consult
    assert "sleep" in consult


@pytest.mark.asyncio
async def test_mandatory_consults_skip_peers_not_in_candidate_list():
    """If a mandated peer isn't a candidate for this agent, drop it silently."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=SimpleNamespace(
        content=json.dumps({"skill": "get_workout_recommendations", "consult": []})
    ))
    _, consult = await infer_skill_and_consults(
        message="anything",
        skills=["get_workout_recommendations"],
        candidate_peers=["sleep"],  # recovery missing on purpose
        metadata=None,
        llm=llm,
    )
    assert "sleep" in consult
    assert "recovery" not in consult


@pytest.mark.asyncio
async def test_mandatory_consults_do_not_duplicate_when_llm_already_picked_them():
    """LLM picks recovery; whitelist also says recovery — final list still has one."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=SimpleNamespace(
        content=json.dumps({
            "skill": "get_workout_recommendations",
            "consult": ["recovery"],
        })
    ))
    _, consult = await infer_skill_and_consults(
        message="anything",
        skills=["get_workout_recommendations"],
        candidate_peers=["recovery", "sleep"],
        metadata=None,
        llm=llm,
    )
    assert consult.count("recovery") == 1


@pytest.mark.asyncio
async def test_non_whitelisted_skill_keeps_default_behaviour():
    """analyze_workout is not whitelisted; LLM consult is used as-is."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=SimpleNamespace(
        content=json.dumps({"skill": "analyze_workout", "consult": []})
    ))
    _, consult = await infer_skill_and_consults(
        message="как тренировки",
        skills=["analyze_workout"],
        candidate_peers=["recovery", "sleep"],
        metadata=None,
        llm=llm,
    )
    assert consult == []


@pytest.mark.asyncio
async def test_focus_sources_override_still_wins_over_mandatory_consults():
    """User-side focus_sources is the strongest hint — mandatory whitelist
    does not override an explicit override."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock()  # must NOT be called
    skill_id, consult = await infer_skill_and_consults(
        message="anything",
        skills=["get_workout_recommendations"],
        candidate_peers=["sleep", "recovery"],
        metadata={
            "skillId": "get_workout_recommendations",
            "focus_sources": ["sleep"],
        },
        llm=llm,
    )
    assert consult == ["sleep"]
    llm.ainvoke.assert_not_awaited()
