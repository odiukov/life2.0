import pytest


def test_agent_card_has_required_fields():
    from agents.nutrition.app.skills import build_agent_card

    card = build_agent_card()
    assert card.name == "nutrition-agent"
    assert card.protocol_version.startswith("0.")
    assert card.capabilities.streaming is True
    assert card.capabilities.push_notifications is False
    skill_ids = {s.id for s in card.skills}
    assert skill_ids == {
        "log_meal",
        "analyze_nutrition",
        "get_nutrition_recommendations",
        "set_body_profile",
    }


def test_skill_prompts_covers_all_skills():
    from agents.nutrition.app.skills import SKILL_PROMPTS

    assert set(SKILL_PROMPTS.keys()) == {
        "log_meal",
        "analyze_nutrition",
        "get_nutrition_recommendations",
        "set_body_profile",
    }


@pytest.mark.asyncio
async def test_analyze_nutrition_prompt_uses_message_and_params(monkeypatch):
    from agents.nutrition.app import skills

    async def _mock_build(task, params, peer_artifacts=None):
        return f"STUB::{task}::{params.get('message', '')}"

    monkeypatch.setattr(skills, "build_nutrition_prompt", _mock_build)
    prompt = await skills.SKILL_PROMPTS["analyze_nutrition"](
        "как питание", {"peer_artifacts": {"workout": "ok"}}
    )
    assert prompt == "STUB::analyze_nutrition::как питание"


def test_peer_skills_maps_to_sleep_and_workout():
    # new contract: nutrition consults 5 peers (workout, body, sleep, mood, medication)
    # per spec §1 of agent-personas-and-isolation-design
    from agents.nutrition.app.skills import PEER_SKILLS

    assert PEER_SKILLS == {
        "workout": "analyze_workout",
        "body": "analyze_body_trend",
        "sleep": "analyze_sleep",
        "mood": "analyze_mood",
        "medication": "analyze_adherence",
    }
