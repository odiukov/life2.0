"""Every analytical/recommendation prompt must contain GROUNDING_RULES."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.test_persona_present import (  # type: ignore[import-not-found]
    ANALYTICAL_TASKS, _common_patches,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "agent,task",
    [(a, t) for a, ts in ANALYTICAL_TASKS.items() for t in ts],
)
async def test_grounding_rules_in_analytical_prompt(agent, task):
    from shared.grounding import GROUNDING_RULES
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
                text = await builder(task, {"user_id": "00000000-0000-0000-0000-000000000001"})
        else:
            try:
                text = await builder(task, {"user_id": "00000000-0000-0000-0000-000000000001"})
            except TypeError:
                text = await builder(task, {"user_id": "00000000-0000-0000-0000-000000000001"}, peer_artifacts=None)
    finally:
        for p in patches:
            p.stop()

    # Match a stable substring early in GROUNDING_RULES.
    assert "GROUNDING RULES — strict:" in text, \
        f"{agent}.{task}: GROUNDING_RULES missing"
