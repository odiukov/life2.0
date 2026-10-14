import typing

import pytest


def test_kitchen_tool_exposes_only_conversational_skills():
    from orchestrator.app.health_agent import ask_kitchen_agent

    fn = (
        ask_kitchen_agent.coroutine
        if hasattr(ask_kitchen_agent, "coroutine")
        else ask_kitchen_agent
    )
    allowed = set(typing.get_args(typing.get_type_hints(fn)["skill"]))
    assert allowed == {"kitchen.update_inventory", "kitchen.query"}
    assert "verbatim" in ask_kitchen_agent.description


async def test_kitchen_tool_calls_the_kitchen_peer(monkeypatch):
    from orchestrator.app import health_agent

    seen = {}

    async def fake_call(agent, message, skill, user_id=None, focus_sources=None):
        seen.update(agent=agent, message=message, skill=skill, user_id=user_id)
        return "Записал: молоко", None, None

    monkeypatch.setattr(health_agent, "_call_agent_with_artifact", fake_call)
    fn = health_agent.ask_kitchen_agent.coroutine
    command = await fn(
        message="купил молоко",
        skill="kitchen.update_inventory",
        tool_call_id="t1",
        state={"userId": "00000000-0000-0000-0000-000000000001", "toolCalls": []},
    )
    assert seen == {
        "agent": "kitchen",
        "message": "купил молоко",
        "skill": "kitchen.update_inventory",
        "user_id": "00000000-0000-0000-0000-000000000001",
    }
    assert command.update["messages"][0].content == "Записал: молоко"


def test_kitchen_tool_is_registered_and_prompt_mentions_it():
    from orchestrator.app import health_agent

    assert "ask_kitchen_agent" in health_agent._SYSTEM_PROMPT


@pytest.mark.parametrize("skill", ["kitchen.update_inventory", "kitchen.query"])
async def test_kitchen_reply_question_is_preserved_and_call_is_observable(monkeypatch, skill):
    from orchestrator.app import health_agent

    reply = "Какое молоко?\n1. Первое\n2. Второе"

    async def fake_call(agent, message, skill, user_id=None, focus_sources=None):
        return reply, None, []

    monkeypatch.setattr(health_agent, "_call_agent_with_artifact", fake_call)
    command = await health_agent.ask_kitchen_agent.coroutine(
        message="первое", skill=skill, tool_call_id="kitchen-1", state={"toolCalls": []}
    )
    assert command.update["messages"][0].content == reply
    assert command.update["messages"][0].tool_call_id == "kitchen-1"
    call = command.update["toolCalls"][0]
    assert (call["name"], call["skill"], call["status"], call["consultedPeers"]) == (
        "ask_kitchen_agent",
        skill,
        "done",
        [],
    )


async def test_kitchen_tool_is_registered_with_react_agent(monkeypatch):
    from orchestrator.app import health_agent, mcp_tools
    import langgraph.prebuilt

    async def no_mcp():
        return []

    def capture(llm, tools, **kwargs):
        return tools

    monkeypatch.setattr(health_agent, "build_llm", lambda: object())
    monkeypatch.setattr(mcp_tools, "load_mcp_tools", no_mcp)
    monkeypatch.setattr(langgraph.prebuilt, "create_react_agent", capture)
    tools = await health_agent.create_health_agent()
    assert health_agent.ask_kitchen_agent in tools
