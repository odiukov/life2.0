import pytest


def test_agent_card_has_required_fields():
    from agents.workout.app.skills import build_agent_card

    card = build_agent_card()
    assert card.name == "workout-agent"
    assert card.protocol_version.startswith("0.")
    assert card.capabilities.streaming is True
    assert card.capabilities.push_notifications is False
    skill_ids = {s.id for s in card.skills}
    assert skill_ids == {"log_workout", "analyze_workout", "get_workout_recommendations"}


def test_skill_prompts_covers_all_skills():
    from agents.workout.app.skills import SKILL_PROMPTS

    assert set(SKILL_PROMPTS.keys()) == {"log_workout", "analyze_workout", "get_workout_recommendations"}


@pytest.mark.asyncio
async def test_analyze_workout_prompt_uses_message_and_params(monkeypatch):
    from agents.workout.app import skills

    async def _mock_build(task, params, peer_artifacts=None):
        return f"STUB::{task}::{params.get('message', '')}"

    monkeypatch.setattr(skills, "build_workout_prompt", _mock_build)
    prompt = await skills.SKILL_PROMPTS["analyze_workout"]("как тренировки", {"peer_artifacts": {"sleep": "ok"}})
    assert prompt == "STUB::analyze_workout::как тренировки"
