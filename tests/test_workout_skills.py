import pytest


def test_agent_card_has_required_fields():
    from agents.workout.app.skills import build_agent_card

    card = build_agent_card()
    assert card.name == "workout-agent"
    assert card.protocol_version.startswith("0.")
    assert card.capabilities.streaming is True
    assert card.capabilities.push_notifications is False
    skill_ids = {s.id for s in card.skills}
    assert skill_ids == {"log_workout", "analyze_workout", "get_workout_recommendations", "briefing"}


def test_skill_prompts_covers_all_skills():
    from agents.workout.app.skills import SKILL_PROMPTS

    assert set(SKILL_PROMPTS.keys()) == {"log_workout", "analyze_workout", "get_workout_recommendations", "briefing"}


@pytest.mark.asyncio
async def test_briefing_prompt_includes_activity_and_calories():
    from agents.workout.app.skills import SKILL_PROMPTS

    prompt_fn = SKILL_PROMPTS["briefing"]
    prompt = await prompt_fn("", {
        "first_name": "Morning run",
        "total_distance_meters": 5200,
        "total_calories": 420,
        "activity_count": 2,
    })
    assert "Morning run" in prompt
    assert "5.2 km" in prompt
    assert "420 kcal" in prompt
    assert "Activities: 2" in prompt


@pytest.mark.asyncio
async def test_analyze_workout_prompt_uses_message_and_params(monkeypatch):
    from agents.workout.app import skills

    async def _mock_build(task, params, peer_artifacts=None):
        return f"STUB::{task}::{params.get('message', '')}"

    monkeypatch.setattr(skills, "build_workout_prompt", _mock_build)
    prompt = await skills.SKILL_PROMPTS["analyze_workout"]("как тренировки", {"peer_artifacts": {"sleep": "ok"}})
    assert prompt == "STUB::analyze_workout::как тренировки"
