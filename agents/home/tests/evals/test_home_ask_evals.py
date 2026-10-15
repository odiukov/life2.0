"""Real model against recorded HA tools; mutations must never execute."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from home.adapters.agent import LangGraphHomeAgent
from langchain_core.tools import tool
from shared.adapters.chat_model.factory import LangChainChatModelFactory
from shared.config import BaseServiceSettings
from shared.ports.household_credentials import HouseholdConnection
from shared.ports.llm import LLMTask
from shared.testing.evals import real_llm_or_skip

pytestmark = pytest.mark.evals


@tool
async def GetLiveContext() -> str:
    """Read live state and exposed entities."""
    return "Living room light: on. Kitchen light: on, brightness 100. Bedroom temperature: 21 C."


@tool
async def HassTurnOn(name: str = "", area: str = "", domain: str = "") -> str:
    """Turn on an exposed entity or area."""
    pytest.fail("mutating_tool_executed")


@tool
async def HassTurnOff(name: str = "", area: str = "", domain: str = "") -> str:
    """Turn off an exposed entity or area."""
    pytest.fail("mutating_tool_executed")


@tool
async def HassLightSet(name: str = "", area: str = "", brightness: int = 100) -> str:
    """Set a light's brightness percentage from 0 to 100."""
    pytest.fail("mutating_tool_executed")


class RecordedPool:
    async def tools(self, conn):
        return [GetLiveContext, HassTurnOn, HassTurnOff, HassLightSet]


@pytest.mark.parametrize(
    ("locale", "question", "expected"),
    [
        ("ru", "выключи свет в гостиной", "HassTurnOff"),
        ("en", "turn off the living room light", "HassTurnOff"),
        ("ru", "сделай свет на кухне на 40%", "HassLightSet"),
        ("en", "set the kitchen light to 40%", "HassLightSet"),
        ("ru", "какая температура в спальне?", None),
        ("en", "what is the bedroom temperature?", None),
        ("ru", "включи всё", "at_most_one"),
        ("en", "turn everything on", "at_most_one"),
    ],
)
async def test_home_questions_only_propose_changes(locale, question, expected) -> None:
    settings = BaseServiceSettings.model_validate(
        {"database": {"dsn": "postgresql://unused@localhost/unused"}}
    )
    real_llm_or_skip(settings, LLMTask.SMART)
    conn = HouseholdConnection(uuid4(), {}, 1, None, None, datetime.now(UTC))
    outcome = await LangGraphHomeAgent(LangChainChatModelFactory(settings), RecordedPool()).run(
        question, conn, locale
    )
    if expected is None:
        assert outcome.proposal is None
        assert "21" in outcome.text
    elif expected == "at_most_one":
        if outcome.proposal is not None:
            assert outcome.proposal.tool == "HassTurnOn"
    else:
        assert outcome.proposal is not None
        assert outcome.proposal.tool == expected
        if expected == "HassLightSet":
            assert outcome.proposal.args["brightness"] == 40
