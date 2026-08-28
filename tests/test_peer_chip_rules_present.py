"""PEER_CHIP_RULES must appear in any prompt that received non-empty peer
artifacts, and must NOT appear when peer_artifacts is empty/None — otherwise
the LLM gets instructions to drop chips for sections that don't exist."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.test_persona_present import (  # type: ignore[import-not-found]
    ANALYTICAL_TASKS, _common_patches,
)


PEER_TASKS_BY_AGENT = {
    "sleep": ["analyze_sleep", "get_recommendations"],
    "workout": ["analyze_workout", "get_recommendations"],
    "nutrition": ["analyze_nutrition", "get_recommendations"],
    "body": ["analyze_body_trend"],
    "mood": ["analyze_mood", "get_mood_recommendations"],
    "habits": ["analyze_habit"],
    "recovery": ["get_readiness", "analyze_recovery_trend", "get_recommendations"],
    "medication": ["analyze_adherence"],
}


def _stub_peer(agent: str) -> dict:
    """Provide a non-empty peer_artifacts dict for one consultable peer."""
    pick = {
        "sleep": ("workout", "training summary"),
        "workout": ("recovery", "recovery state summary"),
        "nutrition": ("workout", "training summary"),
        "body": ("nutrition", "intake summary"),
        "mood": ("sleep", "sleep summary"),
        "habits": ("mood", "mood summary"),
        "recovery": ("sleep", "sleep summary"),
        "medication": ("mood", "mood summary"),
    }
    name, text = pick[agent]
    return {name: text}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "agent,task",
    [(a, t) for a, ts in PEER_TASKS_BY_AGENT.items() for t in ts],
)
async def test_peer_chip_rules_present_when_artifacts_present(agent, task):
    prompt_mod = __import__(f"agents.{agent}.app.prompt", fromlist=["*"])
    builder = getattr(prompt_mod, f"build_{agent}_prompt")
    patches = _common_patches(prompt_mod)
    for p in patches:
        p.start()
    try:
        if agent == "recovery":
            async def _metrics(*_a, **_k):
                return {"2026-05-01": {"hrv": 50, "rhr": 60}}
            with patch.object(prompt_mod, "fetch_recovery_metrics", _metrics):
                text = await builder(
                    task,
                    {"user_id": "00000000-0000-0000-0000-000000000001"},
                    peer_artifacts=_stub_peer(agent),
                )
        else:
            try:
                text = await builder(
                    task,
                    {"user_id": "00000000-0000-0000-0000-000000000001"},
                    peer_artifacts=_stub_peer(agent),
                )
            except TypeError:
                # Builders without peer_artifacts kwarg (e.g. medication's
                # `(skill_id, params)` signature) — pass artifacts via params.
                text = await builder(
                    task,
                    {"user_id": "00000000-0000-0000-0000-000000000001",
                     "peer_artifacts": _stub_peer(agent)},
                )
    finally:
        for p in patches:
            p.stop()
    assert "drop a slash-mention right after the fact" in text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "agent,task",
    [(a, t) for a, ts in PEER_TASKS_BY_AGENT.items() for t in ts],
)
async def test_peer_chip_rules_absent_when_no_artifacts(agent, task):
    prompt_mod = __import__(f"agents.{agent}.app.prompt", fromlist=["*"])
    builder = getattr(prompt_mod, f"build_{agent}_prompt")
    patches = _common_patches(prompt_mod)
    for p in patches:
        p.start()
    try:
        if agent == "recovery":
            async def _metrics(*_a, **_k):
                return {"2026-05-01": {"hrv": 50, "rhr": 60}}
            with patch.object(prompt_mod, "fetch_recovery_metrics", _metrics):
                text = await builder(
                    task,
                    {"user_id": "00000000-0000-0000-0000-000000000001"},
                    peer_artifacts=None,
                )
        else:
            try:
                text = await builder(
                    task,
                    {"user_id": "00000000-0000-0000-0000-000000000001"},
                    peer_artifacts=None,
                )
            except TypeError:
                # Builders without peer_artifacts kwarg.
                text = await builder(
                    task,
                    {"user_id": "00000000-0000-0000-0000-000000000001"},
                )
    finally:
        for p in patches:
            p.stop()
    assert "drop a slash-mention right after the fact" not in text
