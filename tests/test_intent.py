import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.intent import infer_skill_and_consults


@pytest.mark.asyncio
async def test_metadata_skill_short_circuits_llm():
    """When metadata.skillId is provided and valid, LLM is never called."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock()  # must NOT be invoked
    skill_id, consult = await infer_skill_and_consults(
        message="посоветуй тренировку",
        skills=["log_workout", "analyze_workout", "get_workout_recommendations"],
        candidate_peers=["sleep", "nutrition"],
        metadata={"skillId": "get_workout_recommendations"},
        llm=llm,
    )
    assert skill_id == "get_workout_recommendations"
    # MANDATORY_CONSULTS injects recovery+sleep for this skill (recovery
    # filtered out by candidate_peers); explicit metadata.skillId still
    # short-circuits the LLM.
    assert consult == ["sleep"]
    llm.ainvoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_metadata_focus_sources_overrides_llm_consult():
    """When metadata.focus_sources is provided, consult list comes from there."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock()  # must NOT be invoked
    skill_id, consult = await infer_skill_and_consults(
        message="anything",
        skills=["analyze_workout"],
        candidate_peers=["sleep", "nutrition"],
        metadata={"skillId": "analyze_workout", "focus_sources": ["sleep"]},
        llm=llm,
    )
    assert skill_id == "analyze_workout"
    assert consult == ["sleep"]
    llm.ainvoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_focus_sources_filtered_to_candidates():
    """focus_sources values not in candidate_peers are dropped silently."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock()
    skill_id, consult = await infer_skill_and_consults(
        message="anything",
        skills=["analyze_workout"],
        candidate_peers=["sleep", "nutrition"],
        metadata={"skillId": "analyze_workout", "focus_sources": ["sleep", "bogus"]},
        llm=llm,
    )
    assert consult == ["sleep"]


@pytest.mark.asyncio
async def test_no_metadata_calls_llm_once_returns_skill_and_consult():
    """Without metadata, one LLM call returns both skill_id and consult list."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=SimpleNamespace(
        content=json.dumps({
            "skill": "get_workout_recommendations",
            "consult": ["sleep", "nutrition"],
        })
    ))
    skill_id, consult = await infer_skill_and_consults(
        message="посоветуй тренировку с учётом сна и питания",
        skills=["log_workout", "analyze_workout", "get_workout_recommendations"],
        candidate_peers=["sleep", "nutrition"],
        metadata=None,
        llm=llm,
    )
    assert skill_id == "get_workout_recommendations"
    assert consult == ["sleep", "nutrition"]
    assert llm.ainvoke.await_count == 1


@pytest.mark.asyncio
async def test_llm_returns_unknown_skill_yields_none():
    """If LLM picks a skill not in the allowed set, skill_id is None."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=SimpleNamespace(
        content=json.dumps({"skill": "fake_skill", "consult": []})
    ))
    skill_id, consult = await infer_skill_and_consults(
        message="мусор",
        skills=["analyze_workout"],
        candidate_peers=["sleep"],
        metadata=None,
        llm=llm,
    )
    assert skill_id is None
    assert consult == []


@pytest.mark.asyncio
async def test_llm_invalid_json_returns_none_and_empty_consult():
    """Garbage LLM output: skill_id None, consult empty — caller fails the request cleanly."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=SimpleNamespace(content="not json at all"))
    skill_id, consult = await infer_skill_and_consults(
        message="anything",
        skills=["analyze_workout"],
        candidate_peers=["sleep"],
        metadata=None,
        llm=llm,
    )
    assert skill_id is None
    assert consult == []


@pytest.mark.asyncio
async def test_llm_consult_filtered_to_candidates():
    """LLM hallucinating a peer not in candidate_peers is dropped."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=SimpleNamespace(
        content=json.dumps({"skill": "analyze_workout", "consult": ["sleep", "ghost_agent"]})
    ))
    _, consult = await infer_skill_and_consults(
        message="anything",
        skills=["analyze_workout"],
        candidate_peers=["sleep", "nutrition"],
        metadata=None,
        llm=llm,
    )
    assert consult == ["sleep"]


@pytest.mark.asyncio
async def test_llm_exception_returns_none():
    """Network error / provider failure: caller decides what to do."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=RuntimeError("provider down"))
    skill_id, consult = await infer_skill_and_consults(
        message="anything",
        skills=["analyze_workout"],
        candidate_peers=[],
        metadata=None,
        llm=llm,
    )
    assert skill_id is None
    assert consult == []
