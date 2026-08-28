"""Every analytical/recommendation prompt must start with the agent's
IDENTITY block (or contain it verbatim early on). Empty-state and
JSON-only prompts (log_*, define_*) are exempt — they have
their own structured tails."""
from __future__ import annotations

from unittest.mock import patch

import pytest

ANALYTICAL_TASKS = {
    # skills.py passes the bare task name "get_recommendations" to build_X_prompt;
    # the AgentCard skill IDs (Sleep.RECOMMENDATIONS, etc.) are a separate layer.
    "sleep": ["analyze_sleep", "get_recommendations"],
    "workout": ["analyze_workout", "get_recommendations"],
    "nutrition": ["analyze_nutrition", "get_recommendations"],
    "body": ["analyze_body_trend"],
    "mood": ["analyze_mood", "get_mood_recommendations"],
    "habits": ["analyze_habit"],
    "recovery": ["get_readiness", "analyze_recovery_trend", "get_recommendations"],
    "medication": ["analyze_adherence"],
}


async def _zero(*_a, **_k):
    return []


async def _none(*_a, **_k):
    return None


async def _zero_dict(*_a, **_k):
    return {}


def _common_patches(prompt_mod):
    """Patch every DB/vector accessor the prompt module touches with no-data stubs."""
    targets = []
    for name in [
        "fetch_recent_logs", "fetch_body_logs", "fetch_mood_logs",
        "fetch_active_habits", "fetch_habit_logs", "fetch_recovery_metrics",
        "fetch_medication_logs", "search_memories", "get_body_profile",
    ]:
        if hasattr(prompt_mod, name):
            stub = _none if name == "get_body_profile" else _zero
            targets.append(patch.object(prompt_mod, name, stub))
    return targets


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "agent,task",
    [(a, t) for a, ts in ANALYTICAL_TASKS.items() for t in ts],
)
async def test_persona_identity_in_analytical_prompt(agent, task):
    from shared.personas import IDENTITY
    prompt_mod = __import__(f"agents.{agent}.app.prompt", fromlist=["*"])
    builder = getattr(prompt_mod, f"build_{agent}_prompt")
    patches = _common_patches(prompt_mod)
    for p in patches:
        p.start()
    try:
        # Recovery's prompt also needs metrics shaped like a dict-of-dicts;
        # an empty dict triggers the no-data short-circuit but for that path
        # the persona is irrelevant. Force a tiny synthetic snapshot.
        if agent == "recovery":
            async def _metrics(*_a, **_k):
                return {"2026-05-01": {"hrv": 50, "rhr": 60}}
            with patch.object(prompt_mod, "fetch_recovery_metrics", _metrics):
                text = await builder(task, {"user_id": "00000000-0000-0000-0000-000000000001"})
        else:
            try:
                text = await builder(task, {"user_id": "00000000-0000-0000-0000-000000000001"})
            except TypeError:
                # Builders that take peer_artifacts kwarg.
                text = await builder(task, {"user_id": "00000000-0000-0000-0000-000000000001"}, peer_artifacts=None)
    finally:
        for p in patches:
            p.stop()

    # First non-empty line of the identity must be present in the prompt.
    first_identity_line = IDENTITY[agent].splitlines()[0].strip()
    assert first_identity_line in text, \
        f"{agent}.{task}: identity block missing"
