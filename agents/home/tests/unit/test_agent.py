from datetime import UTC, datetime
from uuid import uuid4

from home.adapters.agent import PENDING, LangGraphHomeAgent
from home.domain.actions import ToolCall
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from shared.ports.household_credentials import HouseholdConnection

ran: list[str] = []


@tool
async def GetLiveContext() -> str:
    """Live state of exposed entities."""
    ran.append("GetLiveContext")
    return "Living room lamp: on"


@tool
async def HassTurnOff(name: str) -> str:
    """Turn an entity off."""
    ran.append("HassTurnOff")
    return "done"


class ScriptedModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):  # type: ignore[no-untyped-def]
        return self


class Pool:
    async def tools(self, conn):  # type: ignore[no-untyped-def]
        return [GetLiveContext, HassTurnOff]


class Models:
    def __init__(self, model):  # type: ignore[no-untyped-def]
        self.model = model

    def chat_model(self, task):  # type: ignore[no-untyped-def]
        return self.model


CONN = HouseholdConnection(
    uuid4(), {"base_url": "http://ha", "token": "t"}, 1, None, None, datetime.now(UTC)
)


async def test_reads_run_and_changes_are_captured_not_run() -> None:
    ran.clear()
    model = ScriptedModel(
        responses=[
            AIMessage("", tool_calls=[{"name": "GetLiveContext", "args": {}, "id": "1"}]),
            AIMessage(
                "",
                tool_calls=[
                    {"name": "HassTurnOff", "args": {"name": "Living room lamp"}, "id": "2"}
                ],
            ),
            AIMessage("I will turn off the lamp after confirmation."),
        ]
    )
    outcome = await LangGraphHomeAgent(Models(model), Pool()).run("выключи лампу", CONN, "ru")  # type: ignore[arg-type]
    assert ran == ["GetLiveContext"]
    assert outcome.proposal == ToolCall("HassTurnOff", {"name": "Living room lamp"})
    assert outcome.text == "I will turn off the lamp after confirmation."
    assert PENDING.startswith("Not executed")


async def test_unknown_and_multiple_changes_are_never_executed() -> None:
    @tool
    async def FutureChange(name: str) -> str:
        """Change a future device."""
        raise AssertionError("mutation_executed")

    class FuturePool:
        async def tools(self, conn):
            return [FutureChange, HassTurnOff]

    model = ScriptedModel(
        responses=[
            AIMessage(
                "",
                tool_calls=[
                    {"name": "FutureChange", "args": {"name": "Lamp"}, "id": "1"},
                    {"name": "HassTurnOff", "args": {"name": "Heater"}, "id": "2"},
                ],
            ),
            AIMessage("Please confirm."),
        ]
    )
    ran.clear()
    outcome = await LangGraphHomeAgent(Models(model), FuturePool()).run("change both", CONN, "en")
    assert outcome.proposal == ToolCall("FutureChange", {"name": "Lamp"})
    assert ran == []


async def test_model_transport_failure_is_home_unavailable() -> None:
    import pytest
    from home.application.ports import HomeUnavailable

    class FailingModels:
        def chat_model(self, task):
            raise ConnectionError("private provider details")

    with pytest.raises(HomeUnavailable):
        await LangGraphHomeAgent(FailingModels(), Pool()).run("temperature?", CONN, "en")
