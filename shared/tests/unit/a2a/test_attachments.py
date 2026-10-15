import base64
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
from shared.a2a.request import MAX_ATTACHMENT_BYTES, Envelope, InvalidRequest, to_request
from shared.adapters.a2a.skill_client import A2ASkillClient
from shared.ports.skills import Attachment, SkillCallError
from shared.testing.fakes import FakeLLM, FakeSkillClient, FakeTaskRecords, FixedClock

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
PDF = b"%PDF-1.7\n" + bytes(range(256))


async def echo_files(request, consult) -> SkillResult:
    return SkillResult(
        output="ok",
        data={
            "files": [
                {"name": a.name, "mime": a.mime, "size": len(a.data), "same": a.data == PDF}
                for a in request.attachments
            ]
        },
    )


def app() -> object:
    executor = SkillExecutor(
        agent="finance",
        handlers={"finance.import_statement": echo_files},
        peers=[],
        llm=FakeLLM(),
        task_records=FakeTaskRecords(),
        clock=FixedClock(NOW),
        routable=[],
    )
    card = AgentCard(
        protocol_version="0.3.0",
        name="finance-agent",
        description="t",
        url="http://finance/",
        version="1",
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=[AgentSkill(id="finance.import_statement", name="i", description="i", tags=[])],
    )
    handler = DefaultRequestHandler(agent_executor=executor, task_store=InMemoryTaskStore())
    return A2AStarletteApplication(agent_card=card, http_handler=handler).build()


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app())) as client:
        yield client


async def test_attachment_bytes_survive_the_round_trip(http: httpx.AsyncClient) -> None:
    reply = await A2ASkillClient("http://finance/", http).call(
        skill_id="finance.import_statement",
        user_id=uuid4(),
        params={},
        attachments=[Attachment(name="oct.pdf", mime="application/pdf", data=PDF)],
    )
    assert reply.data == {
        "files": [{"name": "oct.pdf", "mime": "application/pdf", "size": len(PDF), "same": True}]
    }


def _envelope(*files: tuple[str | None, str | None, str]) -> Envelope:
    return Envelope(
        task_id="t", context_id="c", text="", metadata={"user_id": str(uuid4())}, files=files
    )


def test_bad_base64_is_rejected_with_a_code() -> None:
    with pytest.raises(InvalidRequest, match="invalid_attachment"):
        to_request(_envelope(("a.pdf", "application/pdf", "not base64!")), skill_id="s")


def test_oversized_attachments_are_rejected() -> None:
    big = base64.b64encode(b"x" * (MAX_ATTACHMENT_BYTES // 2 + 1)).decode()
    with pytest.raises(InvalidRequest, match="attachment_too_large"):
        to_request(
            _envelope(("a", "application/pdf", big), ("b", "application/pdf", big)), skill_id="s"
        )


def test_missing_name_and_mime_get_safe_defaults() -> None:
    request = to_request(_envelope((None, None, base64.b64encode(b"x").decode())), skill_id="s")
    assert request.attachments == (
        Attachment(name="file", mime="application/octet-stream", data=b"x"),
    )


def test_audit_never_contains_bytes() -> None:
    request = to_request(
        _envelope(("a.pdf", "application/pdf", base64.b64encode(PDF).decode())), skill_id="s"
    )
    assert request.audit()["attachments"] == 1
    assert "a.pdf" not in str(request.audit())


async def test_invalid_attachment_fails_the_task_with_the_code(http: httpx.AsyncClient) -> None:
    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "message/send",
        "params": {
            "message": {
                "kind": "message",
                "role": "user",
                "messageId": "m1",
                "parts": [
                    {
                        "kind": "file",
                        "file": {"name": "a", "mimeType": "application/pdf", "bytes": "%%%"},
                    }
                ],
                "metadata": {
                    "skillId": "finance.import_statement",
                    "user_id": str(uuid4()),
                    "params": {},
                },
            }
        },
    }
    body = (await http.post("http://finance/", json=payload)).json()
    assert body["result"]["status"]["state"] == "failed"
    assert "invalid_attachment" in str(body["result"]["status"]["message"])


async def test_fake_client_records_attachments() -> None:
    from shared.ports.skills import SkillReply

    fake = FakeSkillClient(lambda *args: SkillReply(text="", data={}))
    file = Attachment(name="x", mime="image/png", data=b"\x89PNG")
    await fake.call(skill_id="s", user_id=uuid4(), params={}, attachments=[file])
    await fake.call(skill_id="s", user_id=uuid4(), params={})
    assert fake.attachments == [(file,), ()]
    assert len(fake.calls) == 2


def test_skill_call_error_still_carries_codes() -> None:
    assert SkillCallError("attachment_too_large").code == "attachment_too_large"
