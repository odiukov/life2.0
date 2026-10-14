from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

from a2a.server.agent_execution import RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    DataPart,
    Part,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
    TextPart,
)
from shared.a2a.executor import SkillExecutor, SkillResult
from shared.a2a.request import SkillRequest
from shared.testing.fakes import FakeLLM, FakeTaskRecords, FixedClock

NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)


class Queue:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def enqueue_event(self, event: Any) -> None:
        self.events.append(event)


def ctx(metadata: dict[str, object], text: str = "съел омлет") -> RequestContext:
    message = SimpleNamespace(
        parts=[Part(root=TextPart(text=text))], metadata=metadata, message_id="m"
    )
    return cast(
        RequestContext,
        SimpleNamespace(message=message, task_id=str(uuid4()), context_id=str(uuid4())),
    )


def summary(events: list[Any]) -> list[str]:
    out = []
    for event in events:
        if isinstance(event, TaskStatusUpdateEvent):
            out.append(f"status:{event.status.state.value}{':final' if event.final else ''}")
        elif isinstance(event, TaskArtifactUpdateEvent):
            out.append(f"artifact:{event.artifact.name}")
    return out


def build(
    handler: Any, records: FakeTaskRecords | None = None, llm: FakeLLM | None = None
) -> SkillExecutor:
    return SkillExecutor(
        agent="nutrition",
        handlers={"log_meal": handler, "analyze_nutrition": handler},
        peers=["workout", "sleep"],
        llm=llm or FakeLLM(),
        task_records=records or FakeTaskRecords(),
        clock=FixedClock(NOW),
    )


async def test_success_emits_the_legacy_event_sequence_and_records_the_task() -> None:
    seen: list[tuple[SkillRequest, tuple[str, ...]]] = []

    async def handler(request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        seen.append((request, consult))
        return SkillResult(output="Записал", log_entry=request.text, consulted=("workout",))

    records = FakeTaskRecords()
    queue = Queue()
    uid = uuid4()
    await build(handler, records).execute(
        ctx({"skillId": "log_meal", "user_id": str(uid), "focus_sources": ["workout"]}),
        cast(EventQueue, queue),
    )
    assert summary(queue.events) == [
        "status:working",
        "artifact:log_entry",
        "artifact:consulted_peers",
        "artifact:analysis",
        "status:completed:final",
    ]
    log_entry = queue.events[1].artifact.parts[0].root
    assert isinstance(log_entry, DataPart)
    assert log_entry.data == {"summary": "съел омлет", "timestamp": NOW.isoformat()}
    assert queue.events[2].artifact.parts[0].root.data == {"peers": ["workout"]}
    assert queue.events[3].artifact.parts[0].root.text == "Записал"
    assert seen[0][0].user_id == uid
    assert seen[0][1] == ("workout",)
    assert records.rows[0]["state"] == "completed"
    assert records.rows[0]["skill_id"] == "log_meal"


async def test_unknown_skill_fails_after_working() -> None:
    async def handler(request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        raise AssertionError("not called")

    queue = Queue()
    llm = FakeLLM()
    llm.queue_structured({"skill": "dance", "consult": []})
    await build(handler, llm=llm).execute(ctx({"user_id": str(uuid4())}), cast(EventQueue, queue))
    assert summary(queue.events) == ["status:working", "status:failed:final"]


async def test_missing_user_fails_without_calling_the_handler() -> None:
    called = False

    async def handler(request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        nonlocal called
        called = True
        return SkillResult(output="x")

    queue = Queue()
    await build(handler).execute(ctx({"skillId": "log_meal"}), cast(EventQueue, queue))
    assert summary(queue.events) == ["status:working", "status:failed:final"]
    assert "user_id" in queue.events[-1].status.message.parts[0].root.text
    assert called is False


async def test_peer_calls_get_no_consult_list() -> None:
    seen: list[tuple[str, ...]] = []

    async def handler(request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        seen.append(consult)
        return SkillResult(output="ok")

    await build(handler).execute(
        ctx(
            {
                "skillId": "analyze_nutrition",
                "user_id": str(uuid4()),
                "is_peer_call": True,
                "focus_sources": ["workout"],
            }
        ),
        cast(EventQueue, Queue()),
    )
    assert seen == [()]


async def test_handler_errors_fail_with_a_generic_message_and_no_record() -> None:
    async def handler(request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        raise ValueError("contains user text")

    records = FakeTaskRecords()
    queue = Queue()
    await build(handler, records).execute(
        ctx({"skillId": "log_meal", "user_id": str(uuid4())}), cast(EventQueue, queue)
    )
    assert summary(queue.events) == ["status:working", "status:failed:final"]
    assert queue.events[-1].status.message.parts[0].root.text == "internal error"
    assert records.rows == []


async def test_no_log_entry_still_emits_empty_peers_and_analysis() -> None:
    async def handler(request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        return SkillResult(output="ok")

    queue = Queue()
    await build(handler).execute(
        ctx({"skillId": "log_meal", "user_id": str(uuid4())}), cast(EventQueue, queue)
    )
    assert summary(queue.events) == [
        "status:working",
        "artifact:consulted_peers",
        "artifact:analysis",
        "status:completed:final",
    ]
    assert queue.events[1].artifact.parts[0].root.data == {"peers": []}


async def test_log_entry_uses_explicit_timestamp_and_clips_summary() -> None:
    from datetime import timedelta

    recorded = NOW - timedelta(days=1)

    async def handler(request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        return SkillResult(output="ok", log_entry="  " + "x" * 121 + "  ", log_recorded_at=recorded)

    queue = Queue()
    context = ctx({"skillId": "log_meal", "user_id": str(uuid4())})
    await build(handler).execute(context, cast(EventQueue, queue))
    artifact = queue.events[1]
    assert artifact.artifact.parts[0].root.data == {
        "summary": "x" * 119 + "…",
        "timestamp": recorded.isoformat(),
    }
    for event in queue.events:
        assert event.task_id == context.task_id
        assert event.context_id == context.context_id
        if isinstance(event, TaskArtifactUpdateEvent):
            assert event.append is False
            assert event.last_chunk is True


async def test_record_failure_emits_generic_failure_before_any_artifacts() -> None:
    class BrokenRecords(FakeTaskRecords):
        async def record(self, **kwargs: Any) -> None:
            raise RuntimeError("PRIVATE_RECORD")

    async def handler(request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        return SkillResult(output="PRIVATE_OUTPUT", log_entry="PRIVATE_LOG")

    queue = Queue()
    await build(handler, BrokenRecords()).execute(
        ctx({"skillId": "log_meal", "user_id": str(uuid4())}), cast(EventQueue, queue)
    )
    assert summary(queue.events) == ["status:working", "status:failed:final"]
    assert queue.events[-1].status.message.parts[0].root.text == "internal error"


async def test_unexpected_router_failure_emits_generic_terminal_failure() -> None:
    async def handler(request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        raise AssertionError("not called")

    llm = FakeLLM()
    llm.queue_structured(RuntimeError("PRIVATE_ROUTER"))
    records = FakeTaskRecords()
    queue = Queue()
    await build(handler, records, llm).execute(
        ctx({"user_id": str(uuid4())}, "PRIVATE_INPUT"), cast(EventQueue, queue)
    )
    assert summary(queue.events) == ["status:working", "status:failed:final"]
    assert queue.events[-1].status.message.parts[0].root.text == "internal error"
    assert records.rows == []


async def test_router_receives_working_event_before_llm_call() -> None:
    queue = Queue()

    def respond(call: Any) -> object:
        assert summary(queue.events) == ["status:working"]
        return {"skill": "log_meal", "consult": []}

    async def handler(request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        return SkillResult(output="ok")

    await build(handler, llm=FakeLLM(responder=respond)).execute(
        ctx({"user_id": str(uuid4())}), cast(EventQueue, queue)
    )
    assert summary(queue.events)[-1] == "status:completed:final"


async def test_cancel_emits_only_canceled_final_and_no_record() -> None:
    async def handler(request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        raise AssertionError("not called")

    records = FakeTaskRecords()
    llm = FakeLLM()
    queue = Queue()
    context = ctx({})
    await build(handler, records, llm).cancel(context, cast(EventQueue, queue))
    assert summary(queue.events) == ["status:canceled:final"]
    assert queue.events[0].task_id == context.task_id
    assert records.rows == []
    assert llm.calls == []


async def test_handler_cancellation_propagates_without_failure_or_record() -> None:
    import asyncio

    import pytest

    async def handler(request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        raise asyncio.CancelledError

    queue = Queue()
    records = FakeTaskRecords()
    with pytest.raises(asyncio.CancelledError):
        await build(handler, records).execute(
            ctx({"skillId": "log_meal", "user_id": str(uuid4())}), cast(EventQueue, queue)
        )
    assert summary(queue.events) == ["status:working"]
    assert records.rows == []


async def test_router_cancellation_propagates_without_failure() -> None:
    import asyncio

    import pytest

    async def handler(request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        raise AssertionError("not called")

    queue = Queue()
    llm = FakeLLM()
    llm.queue_structured(asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await build(handler, llm=llm).execute(
            ctx({"user_id": str(uuid4())}), cast(EventQueue, queue)
        )
    assert summary(queue.events) == ["status:working"]


async def test_executor_logs_only_identifiers_and_safe_exception_types(capsys: Any) -> None:
    import json
    import logging

    import structlog
    from shared.config import TelemetrySettings
    from shared.observability.logging import configure_logging

    root = logging.getLogger()
    previous_handlers, previous_level = root.handlers[:], root.level
    previous_last_resort = logging.lastResort
    config = structlog.get_config().copy()
    saved = [
        (item, item.handlers[:], item.propagate)
        for item in logging.Logger.manager.loggerDict.values()
        if isinstance(item, logging.Logger)
    ]
    try:
        configure_logging(TelemetrySettings(log_level="INFO", log_format="json"))

        async def success(request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
            return SkillResult(output="PRIVATE_OUTPUT", log_entry="PRIVATE_LOG")

        async def failure(request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
            raise ValueError("PRIVATE_EXCEPTION")

        for handler in (success, failure):
            await build(handler).execute(
                ctx({"skillId": "log_meal", "user_id": str(uuid4())}, "PRIVATE_INPUT"),
                cast(EventQueue, Queue()),
            )
        llm = FakeLLM()
        llm.queue_structured(RuntimeError("PRIVATE_ROUTER"))
        await build(failure, llm=llm).execute(
            ctx({"user_id": str(uuid4())}, "PRIVATE_INPUT"), cast(EventQueue, Queue())
        )
        captured = capsys.readouterr()
        assert "PRIVATE" not in captured.out + captured.err
        lines = [json.loads(line) for line in captured.err.splitlines() if line.startswith("{")]
        completed = next(item for item in lines if item["event"] == "skill_completed")
        assert completed["agent"] == "nutrition"
        assert completed["skill_id"] == "log_meal"
        assert "task_id" in completed
        assert {item.get("error_type") for item in lines if item["event"] == "skill_failed"} == {
            "ValueError",
            "RuntimeError",
        }
        assert structlog.contextvars.get_contextvars() == {}
    finally:
        root.handlers, root.level = previous_handlers, previous_level
        logging.lastResort = previous_last_resort
        for item, handlers, propagate in saved:
            item.handlers, item.propagate = handlers, propagate
        structlog.configure(**config)
        structlog.contextvars.clear_contextvars()


async def test_handler_invalid_request_is_an_internal_error() -> None:
    from shared.a2a.request import InvalidRequest

    async def handler(request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        raise InvalidRequest("PRIVATE_HANDLER_TEXT")

    queue = Queue()
    records = FakeTaskRecords()
    await build(handler, records).execute(
        ctx({"skillId": "log_meal", "user_id": str(uuid4())}), cast(EventQueue, queue)
    )
    assert summary(queue.events) == ["status:working", "status:failed:final"]
    assert queue.events[-1].status.message.parts[0].root.text == "internal error"
    assert records.rows == []


async def test_failed_handler_result_emits_only_localized_final_failure_without_record() -> None:
    async def handler(request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        return SkillResult(
            output="Provider temporarily unavailable.",
            failed=True,
            log_entry="must not emit",
            consulted=("workout",),
        )

    records = FakeTaskRecords()
    queue = Queue()
    await build(handler, records).execute(
        ctx({"skillId": "log_meal", "user_id": str(uuid4())}), cast(EventQueue, queue)
    )
    assert summary(queue.events) == ["status:working", "status:failed:final"]
    assert queue.events[-1].status.message.parts[0].root.text == "Provider temporarily unavailable."
    assert records.rows == []
