import pytest


def test_agent_card_has_required_fields():
    from agents.sleep.app.skills import build_agent_card

    card = build_agent_card()
    assert card.name == "sleep-agent"
    assert card.protocol_version.startswith("0.")
    assert card.capabilities.streaming is True
    assert card.capabilities.push_notifications is False
    skill_ids = {s.id for s in card.skills}
    assert skill_ids == {"log_sleep", "analyze_sleep", "get_sleep_recommendations", "briefing"}


def test_skill_prompts_covers_all_skills():
    from agents.sleep.app.skills import SKILL_PROMPTS

    assert set(SKILL_PROMPTS.keys()) == {"log_sleep", "analyze_sleep", "get_sleep_recommendations", "briefing"}


@pytest.mark.asyncio
async def test_briefing_prompt_includes_duration():
    from agents.sleep.app.skills import SKILL_PROMPTS

    prompt_fn = SKILL_PROMPTS["briefing"]
    prompt = await prompt_fn("", {"duration_seconds": 3600 * 7 + 60 * 23, "deep_sleep_seconds": 3600})
    assert "7h 23m" in prompt
    assert "Deep sleep" in prompt


@pytest.mark.asyncio
async def test_analyze_sleep_prompt_uses_message_and_params(monkeypatch):
    from agents.sleep.app import skills

    async def _mock_build(task, params, peer_artifacts=None):
        return f"STUB::{task}::{params.get('message', '')}"

    monkeypatch.setattr(skills, "build_sleep_prompt", _mock_build)
    prompt = await skills.SKILL_PROMPTS["analyze_sleep"]("как спалось", {"peer_artifacts": {"workout": "ok"}})
    assert prompt == "STUB::analyze_sleep::как спалось"
