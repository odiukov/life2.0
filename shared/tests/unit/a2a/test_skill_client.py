from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from shared.a2a.executor import SkillExecutor, SkillResult
from shared.a2a.request import SkillRequest
from shared.adapters.a2a.skill_client import A2ASkillClient
from shared.ports.skills import SkillCallError, SkillReply, SkillUnavailable
from shared.testing.fakes import FakeLLM, FakeSkillClient, FakeTaskRecords, FixedClock

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)


async def ok(request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
    return SkillResult(
        output="done", data={"echo": dict(request.params), "user": str(request.user_id)}
    )


async def gone(request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
    return SkillResult(output="item_gone", failed=True)


def app() -> object:
    executor = SkillExecutor(
        agent="kitchen",
        handlers={"kitchen.inventory": ok, "kitchen.item_action": gone},
        peers=[],
        llm=FakeLLM(),
        task_records=FakeTaskRecords(),
        clock=FixedClock(NOW),
    )
    card = AgentCard(
        protocol_version="0.3.0",
        name="kitchen-agent",
        description="test",
        url="http://kitchen/",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=[AgentSkill(id="kitchen.inventory", name="i", description="i", tags=[])],
    )
    handler = DefaultRequestHandler(agent_executor=executor, task_store=InMemoryTaskStore())
    return A2AStarletteApplication(agent_card=card, http_handler=handler).build()


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app())) as client:
        yield client


async def test_call_returns_data_and_text(http: httpx.AsyncClient) -> None:
    user = uuid4()
    reply = await A2ASkillClient("http://kitchen/", http).call(
        skill_id="kitchen.inventory", user_id=user, params={"location": "fridge"}
    )
    assert reply.text == "done"
    assert reply.data == {"echo": {"location": "fridge"}, "user": str(user)}


async def test_failed_task_raises_with_code(http: httpx.AsyncClient) -> None:
    with pytest.raises(SkillCallError) as error:
        await A2ASkillClient("http://kitchen/", http).call(
            skill_id="kitchen.item_action", user_id=uuid4(), params={}
        )
    assert error.value.code == "item_gone"


@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ReadTimeout])
async def test_transport_errors_are_unavailable(error_type: type[httpx.HTTPError]) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise error_type("down", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(boom)) as http:
        with pytest.raises(SkillUnavailable):
            await A2ASkillClient("http://kitchen/", http).call(
                skill_id="kitchen.inventory", user_id=uuid4(), params={}
            )


@pytest.mark.parametrize("status_code", [200, 502])
async def test_non_json_reply_is_unavailable(status_code: int) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(status_code, text="bad gateway"))
    ) as http:
        with pytest.raises(SkillUnavailable):
            await A2ASkillClient("http://kitchen/", http).call(
                skill_id="kitchen.inventory", user_id=uuid4(), params={}
            )


@pytest.mark.parametrize(
    "result",
    [
        {"id": "t", "contextId": "c", "status": "broken"},
        {"id": "t", "contextId": "c", "status": {"state": "failed", "message": "broken"}},
        {"id": "t", "contextId": "c", "status": {"state": "completed"}, "artifacts": 1},
        {
            "id": "t",
            "contextId": "c",
            "status": {"state": "completed"},
            "artifacts": [{"artifactId": "a", "name": "analysis", "parts": 1}],
        },
        {"id": "t", "contextId": "c", "status": {"state": "working"}},
        {"status": {"state": "completed"}},
    ],
)
async def test_malformed_or_incomplete_task_is_unavailable(result: dict[str, object]) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"result": result}))
    ) as http:
        with pytest.raises(SkillUnavailable):
            await A2ASkillClient("http://kitchen/", http).call(
                skill_id="kitchen.inventory", user_id=uuid4(), params={}
            )


async def test_http_error_with_json_task_is_unavailable() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                503, json={"result": {"kind": "task", "status": {"state": "completed"}}}
            )
        )
    ) as http:
        with pytest.raises(SkillUnavailable):
            await A2ASkillClient("http://kitchen/", http).call(
                skill_id="kitchen.inventory", user_id=uuid4(), params={}
            )


async def test_optional_data_and_empty_failed_message() -> None:
    state = "completed"

    def reply(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"result": {"id": "t", "contextId": "c", "status": {"state": state}}}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as http:
        client = A2ASkillClient("http://kitchen/", http)
        assert await client.call(
            skill_id="kitchen.inventory", user_id=uuid4(), params={}
        ) == SkillReply(text="", data=None)
        state = "failed"
        with pytest.raises(SkillCallError) as error:
            await client.call(skill_id="kitchen.inventory", user_id=uuid4(), params={})
        assert error.value.code == "failed"


async def test_fake_records_calls_and_propagates_failures() -> None:
    user = uuid4()
    outcome = SkillReply(text="done", data={"items": []})
    client = FakeSkillClient(lambda skill, user, params, text: outcome)
    assert (
        await client.call(
            skill_id="kitchen.inventory", user_id=user, params={"location": "fridge"}, text="query"
        )
        == outcome
    )
    assert client.calls == [("kitchen.inventory", user, {"location": "fridge"}, "query")]
    unavailable = SkillUnavailable("offline")
    failing = FakeSkillClient(lambda skill, user, params, text: unavailable)
    with pytest.raises(SkillUnavailable) as error:
        await failing.call(skill_id="kitchen.inventory", user_id=user, params={})
    assert error.value is unavailable
    assert failing.calls == [("kitchen.inventory", user, {}, "")]
