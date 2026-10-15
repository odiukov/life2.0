import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from a2a.types import Message, Part, TextPart
from nutrition.adapters.a2a.card import PEER_SKILLS, SKILLS, build_agent_card
from nutrition.composition import build_runtime
from nutrition.settings import NutritionSettings
from nutrition.testing import FakeSync
from shared.a2a.executor import SkillExecutor, SkillResult
from shared.skill_ids import Dashboard, Nutrition
from shared.testing.fakes import FakeLLM, FakePeerClient, FixedClock, InMemoryVectorMemory

EXPECTED_IDS = {
    v for k, v in vars(Nutrition).items() if not k.startswith("_") and isinstance(v, str)
}


def test_card_declares_exactly_the_shared_skill_ids() -> None:
    assert {s.id for s in SKILLS} == EXPECTED_IDS | {Dashboard.CARD, Dashboard.DETAIL}


def test_card_identity_is_unchanged() -> None:
    card = build_agent_card("http://agent-nutrition:8003/")
    assert card.name == "nutrition-agent"
    assert card.url == "http://agent-nutrition:8003/"
    assert card.version == "1.0.0"
    assert card.capabilities.streaming is True
    assert card.protocol_version == "0.3.0"


def test_peer_graph_is_unchanged() -> None:
    assert set(PEER_SKILLS) == {"workout", "body", "sleep", "mood", "medication"}


def test_every_card_skill_has_a_handler() -> None:
    settings = NutritionSettings.model_validate(
        {"database": {"dsn": "postgresql://u:p@localhost:1/x"}}
    )
    runtime = build_runtime(
        settings,
        llm=FakeLLM(),
        memory=InMemoryVectorMemory(),
        peers=FakePeerClient(),
        sync=FakeSync(),
    )
    assert set(runtime.executor.skill_ids) == EXPECTED_IDS | {Dashboard.CARD, Dashboard.DETAIL}


# Recorded from the legacy executor before its deletion. Only generated UUIDs
# and timestamps are normalized; fields, values and event order are preserved.
LEGACY = json.loads(
    (Path(__file__).resolve().parents[4] / "tests/fixtures/nutrition_legacy_a2a.json").read_text()
)


def test_complete_card_and_peer_mapping_match_the_recorded_legacy_contract() -> None:
    card = build_agent_card("http://agent-nutrition:8003/").model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    assert {s["id"] for s in card["skills"] if "structured" in s["tags"]} == {
        Dashboard.CARD,
        Dashboard.DETAIL,
    }
    card["skills"] = [
        s for s in card["skills"] if s["id"] not in {Dashboard.CARD, Dashboard.DETAIL}
    ]
    assert card == LEGACY["card"]
    assert LEGACY["peers"] == PEER_SKILLS


@pytest.mark.parametrize("skill", sorted(EXPECTED_IDS))
async def test_every_skill_preserves_recorded_status_and_artifact_events(skill: str) -> None:
    async def handler(request, consult):
        return SkillResult(
            output="fixture output",
            log_entry="fixture input" if skill == Nutrition.LOG_MEAL else None,
        )

    records = MagicMock(record=AsyncMock())
    executor = SkillExecutor(
        agent="nutrition",
        handlers={skill: handler},
        peers=list(PEER_SKILLS),
        llm=FakeLLM(),
        task_records=records,
        clock=FixedClock(datetime(2026, 10, 13, 9, tzinfo=UTC)),
    )
    context = MagicMock(task_id="task-1", context_id="ctx-1", current_task=None)
    context.message = Message(
        role="user",
        message_id="m1",
        parts=[Part(root=TextPart(text="fixture input"))],
        metadata={"skillId": skill, "user_id": "00000000-0000-0000-0000-000000000001"},
    )
    queue = MagicMock(enqueue_event=AsyncMock())
    await executor.execute(context, queue)
    events = []
    for call in queue.enqueue_event.await_args_list:
        event = call.args[0].model_dump(mode="json", by_alias=True, exclude_none=True)
        if "artifact" in event:
            event["artifact"]["artifactId"] = "<uuid>"
            for part in event["artifact"]["parts"]:
                if "data" in part and "timestamp" in part["data"]:
                    timestamp = datetime.fromisoformat(part["data"]["timestamp"])
                    assert timestamp.utcoffset().total_seconds() == 0
                    part["data"]["timestamp"] = "<timestamp>"
        events.append(event)
    assert events == LEGACY["events"][skill]
    recorded = records.record.await_args.kwargs
    assert recorded["skill_id"] == skill
    assert recorded["input_"]["user_id"] == "00000000-0000-0000-0000-000000000001"
    assert recorded["state"] == "completed"


LEGACY_FAILURES = json.loads(
    (
        Path(__file__).resolve().parents[4] / "tests/fixtures/nutrition_legacy_failure_a2a.json"
    ).read_text()
)


@pytest.mark.parametrize("skill", sorted(LEGACY_FAILURES))
async def test_failed_skill_preserves_recorded_legacy_failure_event_shape(skill: str) -> None:
    async def handler(request, consult):
        return SkillResult(output="Provider temporarily unavailable.", failed=True)

    records = MagicMock(record=AsyncMock())
    executor = SkillExecutor(
        agent="nutrition",
        handlers={skill: handler},
        peers=list(PEER_SKILLS),
        llm=FakeLLM(),
        task_records=records,
        clock=FixedClock(datetime(2026, 10, 13, 9, tzinfo=UTC)),
    )
    context = MagicMock(task_id="task-1", context_id="ctx-1", current_task=None)
    context.message = Message(
        role="user",
        message_id="m1",
        parts=[Part(root=TextPart(text="fixture input"))],
        metadata={"skillId": skill, "user_id": "00000000-0000-0000-0000-000000000001"},
    )
    queue = MagicMock(enqueue_event=AsyncMock())
    await executor.execute(context, queue)
    events = []
    for call in queue.enqueue_event.await_args_list:
        event = call.args[0].model_dump(mode="json", by_alias=True, exclude_none=True)
        if event.get("status", {}).get("message"):
            message = event["status"]["message"]
            assert message["parts"][0]["text"] == "Provider temporarily unavailable."
            message["messageId"] = "<uuid>"
            message["parts"][0]["text"] = "<failure-message>"
        events.append(event)
    assert events == LEGACY_FAILURES[skill]
    records.record.assert_not_awaited()
