"""set_body_profile is direct-handled by the executor (`_DIRECT_SKILLS`).
The prompt builder must raise loudly if anyone calls it — silent empty
prompts would cause an LLM to reply with whatever it feels like."""
import pytest

pytestmark = pytest.mark.asyncio


async def test_set_body_profile_prompt_raises():
    from agents.nutrition.app.skills import SKILL_PROMPTS
    from shared.skill_ids import Nutrition

    with pytest.raises(NotImplementedError):
        await SKILL_PROMPTS[Nutrition.SET_BODY_PROFILE]("hi", {})
