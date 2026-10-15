from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from orchestrator.adapters.a2a import A2APeerAgents
from orchestrator.application.ports import PeerUnavailable
from shared.a2a.executor import SkillExecutor, SkillResult
from shared.testing.fakes import FakeLLM, FakeTaskRecords, FixedClock

seen: list[dict[str, object]] = []


async def analyze(request, consult):  # type: ignore[no-untyped-def]
    seen.append(
        {"skill": request.skill_id, "user": str(request.user_id), "peer": request.is_peer_call}
    )
    return SkillResult(output="sleep summary", consulted=("nutrition",), data={"x": 1})


async def recommend(request, consult):  # type: ignore[no-untyped-def]
    return SkillResult(output="LLM unavailable", failed=True)


def app() -> object:
    executor = SkillExecutor(
        agent="sleep",
        handlers={"analyze_sleep": analyze, "get_sleep_recommendations": recommend},
        peers=["nutrition"],
        llm=FakeLLM(),
        task_records=FakeTaskRecords(),
        clock=FixedClock(datetime(2026, 10, 14, tzinfo=UTC)),
    )
    card = AgentCard(
        protocol_version="0.3.0",
        name="sleep-agent",
        description="t",
        url="http://sleep/",
        version="1",
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=[AgentSkill(id="analyze_sleep", name="a", description="a", tags=[])],
    )
    return A2AStarletteApplication(
        agent_card=card,
        http_handler=DefaultRequestHandler(agent_executor=executor, task_store=InMemoryTaskStore()),
    ).build()


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app())) as client:
        yield client


async def test_ask_returns_text_consulted_and_data(http: httpx.AsyncClient) -> None:
    user = uuid4()
    reply = await A2APeerAgents({"sleep": "http://sleep/"}, http, timeout_s=5).ask(
        "sleep",
        user_id=user,
        skill="analyze_sleep",
        text="how did I sleep?",
        focus_sources=["nutrition"],
    )
    assert (reply.text, reply.consulted, reply.data, reply.failed) == (
        "sleep summary",
        ("nutrition",),
        {"x": 1},
        False,
    )
    assert seen[-1] == {
        "skill": "analyze_sleep",
        "user": str(user),
        "peer": False,
    }  # the orchestrator is not a peer


async def test_failed_tasks_return_the_agents_message(http: httpx.AsyncClient) -> None:
    reply = await A2APeerAgents({"sleep": "http://sleep/"}, http, timeout_s=5).ask(
        "sleep", user_id=uuid4(), skill="get_sleep_recommendations", text="?", focus_sources=None
    )
    assert reply.failed
    assert reply.text == "LLM unavailable"


async def test_transport_errors_are_unavailable() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(boom)) as http:
        with pytest.raises(PeerUnavailable):
            await A2APeerAgents({"sleep": "http://sleep/"}, http, timeout_s=5).ask(
                "sleep", user_id=uuid4(), skill="analyze_sleep", text="x", focus_sources=None
            )


@pytest.mark.parametrize("state", ["completed", "failed"])
async def test_partial_artifacts_preserve_text_and_actual_consulted_provenance(state: str) -> None:
    task = {
        "kind": "task",
        "id": "t",
        "contextId": "c",
        "status": {
            "state": state,
            "message": {
                "kind": "message",
                "messageId": "m",
                "role": "agent",
                "parts": [{"kind": "text", "text": "failure"}],
            },
        },
        "artifacts": [
            {
                "artifactId": "1",
                "name": "analysis",
                "parts": [{"kind": "text", "text": "first "}, {"kind": "text", "text": "second"}],
            },
            {
                "artifactId": "2",
                "name": "consulted_peers",
                "parts": [{"kind": "data", "data": {"peers": ["nutrition", "nutrition", 42]}}],
            },
            {"artifactId": "3", "name": "data", "parts": [{"kind": "data", "data": {"x": 1}}]},
        ],
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"result": task}))
    ) as http:
        reply = await A2APeerAgents({"sleep": "http://sleep"}, http, timeout_s=5).ask(
            "sleep",
            user_id=uuid4(),
            skill="analyze_sleep",
            text="private health text",
            focus_sources=["body"],
        )
    assert reply.text == "first second"
    assert reply.consulted == ("nutrition",)
    assert reply.data == {"x": 1}
    assert reply.failed is (state == "failed")


@pytest.mark.parametrize(
    "body", [[], None, {}, {"error": {"message": "private"}}, {"result": {"kind": "task"}}]
)
async def test_invalid_protocol_response_is_unavailable(body: object, caplog) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))
    ) as http:
        with pytest.raises(PeerUnavailable) as error:
            await A2APeerAgents({"sleep": "http://sleep"}, http, timeout_s=5).ask(
                "sleep", user_id=uuid4(), skill="analyze_sleep", text="private", focus_sources=None
            )
    assert "private" not in str(error.value)
    assert "private" not in caplog.text


@pytest.mark.parametrize("focus", [None, ["sleep", "nutrition"]])
async def test_wire_request_preserves_text_skill_tenant_and_optional_focus(focus) -> None:
    import json

    user = uuid4()

    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url == "http://workout/"
        assert payload["method"] == "message/send"
        message = payload["params"]["message"]
        assert message["role"] == "user"
        assert message["parts"] == [{"kind": "text", "text": "my exact words"}]
        expected = {"skillId": "get_workout_recommendations", "user_id": str(user)}
        if focus:
            expected["focus_sources"] = focus
        assert message["metadata"] == expected
        return httpx.Response(
            200,
            json={
                "result": {
                    "kind": "task",
                    "id": "t",
                    "contextId": "c",
                    "status": {"state": "completed"},
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        reply = await A2APeerAgents({"workout": "http://workout"}, http, timeout_s=5).ask(
            "workout",
            user_id=user,
            skill="get_workout_recommendations",
            text="my exact words",
            focus_sources=focus,
        )
    assert reply.consulted == ()
    assert reply.data is None


async def test_empty_consulted_artifact_does_not_invent_requested_peers() -> None:
    result = {
        "kind": "task",
        "id": "t",
        "contextId": "c",
        "status": {"state": "completed"},
        "artifacts": [
            {
                "artifactId": "a",
                "name": "consulted_peers",
                "parts": [{"kind": "data", "data": {"peers": []}}],
            }
        ],
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"result": result}))
    ) as http:
        reply = await A2APeerAgents({"workout": "http://workout"}, http, timeout_s=5).ask(
            "workout", user_id=uuid4(), skill="analyze_workout", text="?", focus_sources=["sleep"]
        )
    assert reply.consulted == ()


async def test_unconfigured_peer_is_unavailable_without_http_call() -> None:
    def unexpected(request: httpx.Request) -> httpx.Response:
        pytest.fail("An unconfigured peer must not make an HTTP request")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as http:
        with pytest.raises(PeerUnavailable):
            await A2APeerAgents({}, http, timeout_s=5).ask(
                "sleep", user_id=uuid4(), skill="analyze_sleep", text="?", focus_sources=None
            )
