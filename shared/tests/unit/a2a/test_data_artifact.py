from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

from a2a.server.agent_execution import RequestContext
from a2a.server.events import EventQueue
from a2a.types import DataPart, Part, TaskArtifactUpdateEvent, TaskStatusUpdateEvent, TextPart
from shared.a2a.executor import SkillExecutor, SkillResult
from shared.a2a.request import SkillRequest
from shared.testing.fakes import FakeLLM, FakeTaskRecords, FixedClock

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)


class Queue:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def enqueue_event(self, event: Any) -> None:
        self.events.append(event)


def ctx(metadata: dict[str, object]) -> RequestContext:
    message = SimpleNamespace(
        parts=[Part(root=TextPart(text=""))], metadata=metadata, message_id="m"
    )
    return cast(
        RequestContext,
        SimpleNamespace(message=message, task_id=str(uuid4()), context_id=str(uuid4())),
    )


async def test_data_result_emits_a_data_artifact_before_analysis() -> None:
    seen: list[SkillRequest] = []

    async def handler(request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        seen.append(request)
        return SkillResult(output="ok", data={"items": [], "location": request.params["location"]})

    executor = SkillExecutor(
        agent="kitchen",
        handlers={"kitchen.inventory": handler},
        peers=[],
        llm=FakeLLM(),
        task_records=FakeTaskRecords(),
        clock=FixedClock(NOW),
    )
    queue = Queue()
    await executor.execute(
        ctx(
            {
                "skillId": "kitchen.inventory",
                "user_id": str(uuid4()),
                "params": {"location": "fridge"},
            }
        ),
        cast(EventQueue, queue),
    )
    names = [e.artifact.name for e in queue.events if isinstance(e, TaskArtifactUpdateEvent)]
    assert names == ["consulted_peers", "data", "analysis"]
    data = next(
        e
        for e in queue.events
        if isinstance(e, TaskArtifactUpdateEvent) and e.artifact.name == "data"
    )
    part = data.artifact.parts[0].root
    assert isinstance(part, DataPart)
    assert part.data == {"items": [], "location": "fridge"}
    assert isinstance(queue.events[-1], TaskStatusUpdateEvent)
    assert seen[0].params == {"location": "fridge"}


async def test_failed_result_with_code_is_the_status_message() -> None:
    async def handler(request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        return SkillResult(output="item_gone", failed=True)

    executor = SkillExecutor(
        agent="kitchen",
        handlers={"kitchen.item_action": handler},
        peers=[],
        llm=FakeLLM(),
        task_records=FakeTaskRecords(),
        clock=FixedClock(NOW),
    )
    queue = Queue()
    await executor.execute(
        ctx({"skillId": "kitchen.item_action", "user_id": str(uuid4())}), cast(EventQueue, queue)
    )
    final = queue.events[-1]
    assert final.status.state.value == "failed"
    assert final.status.message.parts[0].root.text == "item_gone"
