from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

from a2a.server.agent_execution import RequestContext
from a2a.server.events import EventQueue
from a2a.types import Part, TextPart
from shared.a2a.executor import SkillExecutor, SkillResult
from shared.a2a.request import SkillRequest
from shared.testing.fakes import FakeLLM, FakeTaskRecords, FixedClock


class Queue:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def enqueue_event(self, event: Any) -> None:
        self.events.append(event)


def ctx(metadata: dict[str, object]) -> RequestContext:
    message = SimpleNamespace(
        parts=[Part(root=TextPart(text="что в холодильнике"))], metadata=metadata, message_id="m"
    )
    return cast(
        RequestContext,
        SimpleNamespace(message=message, task_id=str(uuid4()), context_id=str(uuid4())),
    )


async def ran(request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
    return SkillResult(output=request.skill_id)


def executor(llm: FakeLLM) -> SkillExecutor:
    return SkillExecutor(
        agent="kitchen",
        handlers={"kitchen.query": ran, "kitchen.inventory": ran},
        peers=[],
        llm=llm,
        task_records=FakeTaskRecords(),
        clock=FixedClock(datetime(2026, 10, 14, tzinfo=UTC)),
        routable=["kitchen.query"],
    )


async def test_router_only_sees_routable_skills() -> None:
    llm = FakeLLM()
    llm.queue_structured({"skill": "kitchen.query", "consult": []})
    queue = Queue()
    await executor(llm).execute(ctx({"user_id": str(uuid4())}), cast(EventQueue, queue))
    assert "kitchen.inventory" not in llm.calls[0].system
    assert queue.events[-1].status.state.value == "completed"


async def test_explicit_structured_skill_runs_without_the_router() -> None:
    llm = FakeLLM()
    queue = Queue()
    await executor(llm).execute(
        ctx({"user_id": str(uuid4()), "skillId": "kitchen.inventory"}), cast(EventQueue, queue)
    )
    assert llm.calls == []
    text = [
        e for e in queue.events if getattr(e, "artifact", None) and e.artifact.name == "analysis"
    ]
    assert text[0].artifact.parts[0].root.text == "kitchen.inventory"


async def test_router_cannot_select_registered_structured_handler() -> None:
    llm = FakeLLM()
    llm.queue_structured({"skill": "kitchen.inventory", "consult": []})
    queue = Queue()
    await executor(llm).execute(ctx({"user_id": str(uuid4())}), cast(EventQueue, queue))
    assert queue.events[-1].status.state.value == "failed"


async def test_explicit_conversational_skill_also_bypasses_router() -> None:
    llm = FakeLLM()
    queue = Queue()
    await executor(llm).execute(
        ctx({"user_id": str(uuid4()), "skillId": "kitchen.query"}), cast(EventQueue, queue)
    )
    assert llm.calls == []
    assert queue.events[-1].status.state.value == "completed"


async def test_structured_params_data_artifact_and_failure_status_contract() -> None:
    async def handler(request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        assert request.params == {"location": "freezer"}
        assert consult == ()
        if request.text == "fail":
            return SkillResult(output="conflict", failed=True)
        return SkillResult(output="inventory", data={"items": []})

    llm = FakeLLM()
    records = FakeTaskRecords()
    runner = SkillExecutor(
        agent="kitchen",
        handlers={"kitchen.inventory": handler},
        peers=[],
        llm=llm,
        task_records=records,
        clock=FixedClock(datetime(2026, 10, 14, tzinfo=UTC)),
        routable=[],
    )
    metadata = {
        "user_id": str(uuid4()),
        "skillId": "kitchen.inventory",
        "params": {"location": "freezer"},
    }
    queue = Queue()
    await runner.execute(ctx(metadata), cast(EventQueue, queue))
    data = [
        e.artifact
        for e in queue.events
        if getattr(e, "artifact", None) and e.artifact.name == "data"
    ]
    assert len(data) == 1
    assert data[0].parts[0].root.data == {"items": []}
    assert queue.events[-1].status.state.value == "completed"
    failing = ctx(metadata)
    failing.message.parts[0].root.text = "fail"  # type: ignore[union-attr]
    queue = Queue()
    await runner.execute(failing, cast(EventQueue, queue))
    assert queue.events[-1].status.state.value == "failed"
    assert queue.events[-1].status.message.parts[0].root.text == "conflict"
    assert not any(getattr(e, "artifact", None) for e in queue.events)
    assert len(records.rows) == 1
    assert llm.calls == []
