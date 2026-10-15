"""Real-model checks of the first routing decision; tools are never executed."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
import yaml
from langchain_core.messages import HumanMessage, SystemMessage
from orchestrator.adapters.langgraph.tools import build_tools
from orchestrator.application.ports import RunContext
from orchestrator.prompts import system_prompt
from orchestrator.settings import OrchestratorSettings
from orchestrator.testing import FakeHealthSync, FakePeerAgents, RecordedProposals
from shared.ports.llm import LLMTask
from shared.testing.evals import real_chat_models_or_skip
from shared.testing.fakes import FakeSkillClient

pytestmark = pytest.mark.evals
CASES: list[dict[str, Any]] = yaml.safe_load(
    (Path(__file__).parent / "cases.yaml").read_text("utf-8")
)
NOW = datetime(2026, 10, 14, 9, tzinfo=UTC)
ZONE = ZoneInfo("Europe/Kyiv")


@pytest.fixture(scope="module")
def model():  # type: ignore[no-untyped-def]
    settings = OrchestratorSettings.model_validate(
        {"database": {"dsn": "postgresql://unused@localhost/unused"}}
    )
    return real_chat_models_or_skip(settings).chat_model(LLMTask.SMART)


@pytest.mark.parametrize("case", CASES, ids=[f"case_{i:02d}" for i in range(len(CASES))])
async def test_first_tool_call(case: dict[str, Any], model: Any) -> None:
    lead = case.get("lead")
    ctx = RunContext(uuid4(), uuid4(), None, lead, ZONE, "ru", NOW)
    tools = build_tools(
        ctx,
        last_user_text=case["text"],
        peers=FakePeerAgents(),
        skills=lambda _: FakeSkillClient(lambda *a: RuntimeError("unused_skill")),
        proposals=RecordedProposals(),
        sync=FakeHealthSync(),
    )
    reply = await model.bind_tools(tools).ainvoke(
        [
            SystemMessage(system_prompt(now=NOW, zone=ZONE, lead_agent=lead)),
            HumanMessage(case["text"]),
        ]
    )
    called = {call["name"] for call in reply.tool_calls}
    assert called, "missing_first_tool_call"
    assert called & set(case["expect"]), "wrong_first_tool_call"
    assert not called & set(case.get("forbid", [])), "forbidden_first_tool_call"
