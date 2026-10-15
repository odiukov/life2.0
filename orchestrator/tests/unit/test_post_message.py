import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from orchestrator.application.ports import (
    ChatTaskRepository,
    FinalText,
    InvalidHistory,
    PendingAction,
    PendingActionRepository,
    TaskBusy,
    ToolDone,
    TranscriptMessage,
    TranscriptRepository,
    VisionUnavailable,
)
from orchestrator.application.post_message import EmptyMessage, PostMessage, Run
from orchestrator.application.resolve_action import ResolveAction
from orchestrator.domain.attachments import Upload
from orchestrator.testing import (
    FakeChatGraph,
    FakeDocumentReader,
    FakeImageDescriber,
    in_memory_uow,
)
from shared.adapters.i18n import JsonTranslator
from shared.config import find_locales_dir
from shared.ports.skills import SkillReply
from shared.skill_ids import Body, Finance, Home
from shared.testing.fakes import FakeSkillClient, FixedClock

NOW = datetime(2026, 10, 14, 18, tzinfo=UTC)
TR = JsonTranslator.from_dir(find_locales_dir())
PDF = b"%PDF-1.7 statement"
JPEG = b"\xff\xd8\xff SECRET-IMAGE-BYTES"


@dataclass
class Env:
    post_message: PostMessage
    graph: FakeChatGraph
    uow: Any
    finance: FakeSkillClient
    body: FakeSkillClient
    home: FakeSkillClient
    vision: FakeImageDescriber
    reader: FakeDocumentReader
    user: UUID
    task: UUID

    async def post(self, text: str = "", uploads: list[Upload] | None = None) -> Run:
        return await self.post_message.start(
            self.user, self.task, text=text, timezone="Europe/Kyiv", uploads=uploads or []
        )

    async def messages(self) -> list[TranscriptMessage]:
        async with self.uow.for_user(self.user) as tx:
            return await tx.repo(TranscriptRepository).list(self.user, self.task)

    async def propose(self) -> PendingAction:
        async with self.uow.for_user(self.user) as tx:
            return await tx.repo(PendingActionRepository).propose(
                self.user,
                self.task,
                agent="home",
                kind="home.call_tool",
                payload={"tool": "HassTurnOff"},
                summary="Выключить: Lamp?",
                household_id=None,
                ttl=timedelta(minutes=5),
            )

    async def lead(self, agent: str) -> None:
        async with self.uow.for_user(self.user) as tx:
            await tx.repo(ChatTaskRepository).update(self.user, self.task, {"lead_agent": agent})


def build(
    *,
    reader: FakeDocumentReader | None = None,
    vision: FakeImageDescriber | None = None,
    timeout: float = 5.0,
    busy: bool = False,
) -> Env:
    clock = FixedClock(NOW)
    uow = in_memory_uow(clock)
    graph = FakeChatGraph(busy=busy)
    finance = FakeSkillClient(lambda *a: SkillReply("Импортировано 12 операций.", {"inserted": 12}))
    body = FakeSkillClient(lambda *a: SkillReply("Импортировал 1 измерение.", {"inserted": 1}))
    home = FakeSkillClient(lambda *a: SkillReply("", {"status": "applied"}))
    clients = {"finance": finance, "body": body, "home": home}
    reader = reader or FakeDocumentReader("Payoneer Account Statement")
    vision = vision or FakeImageDescriber()
    resolve = ResolveAction(uow=uow, skills=clients.__getitem__, translator=TR, default_locale="ru")
    post = PostMessage(
        uow=uow,
        graph=graph,
        skills=clients.__getitem__,
        documents=reader,
        vision=vision,
        resolve=resolve,
        clock=clock,
        translator=TR,
        default_locale="ru",
        run_timeout_s=timeout,
    )
    return Env(post, graph, uow, finance, body, home, vision, reader, uuid4(), uuid4())


async def opened(env: Env) -> Env:
    async with env.uow.for_user(env.user) as tx:
        env.task = (
            await tx.repo(ChatTaskRepository).create(
                env.user, lead_agent=None, title=None, household_id=None
            )
        ).id
    return env


@pytest.fixture
async def env() -> Env:
    return await opened(build())


async def collect(run: Run) -> list[dict[str, Any]]:
    return [e async for e in run.events()]


def types(events: list[dict[str, Any]]) -> list[str]:
    return [e["type"] for e in events]


def text_of(events: list[dict[str, Any]]) -> str:
    return "".join(e["delta"] for e in events if e["type"] == "TextMessageContent")


async def test_plain_message_streams_routing_text_and_saves_both_turns(env: Env) -> None:
    env.graph.script([ToolDone("sleep", ("nutrition",)), FinalText("Спал 7 часов.")])
    events = await collect(await env.post("как я спал?"))
    assert types(events) == [
        "RunStarted",
        "TextMessageStart",
        "AgentRouted",
        "TextMessageContent",
        "AgentConsulted",
        "TextMessageEnd",
        "RunFinished",
    ]
    assert events[2]["primary"] == "sleep"
    assert events[4]["peers"] == ["nutrition"]
    assert events[0]["threadId"] == str(env.task)
    assert [(m.role, m.text, m.agent, tuple(m.consulted)) for m in await env.messages()] == [
        ("user", "как я спал?", None, ()),
        ("assistant", "Спал 7 часов.", "sleep", ("nutrition",)),
    ]
    assert env.graph.contexts[0].zone.key == "Europe/Kyiv"


async def test_no_agent_called_routes_to_main(env: Env) -> None:
    env.graph.script([FinalText("Привет!")])
    events = await collect(await env.post("привет"))
    assert [e["primary"] for e in events if e["type"] == "AgentRouted"] == ["main"]
    assert "AgentConsulted" not in types(events)
    assert (await env.messages())[-1].agent is None


async def test_a_proposal_becomes_a_card_and_is_kept_in_the_transcript(env: Env) -> None:
    action = await env.propose()
    env.graph.script(
        [ToolDone("home", proposal_id=action.id), FinalText("Подтверди в приложении.")]
    )
    events = await collect(await env.post("выключи лампу"))
    card = next(e for e in events if e["type"] == "ActionProposed")
    assert card == {
        "type": "ActionProposed",
        "actionId": str(action.id),
        "summary": "Выключить: Lamp?",
        "expiresAt": action.expires_at.isoformat(),
    }
    assert (await env.messages())[-1].action == {
        "id": str(action.id),
        "summary": "Выключить: Lamp?",
        "status": "pending",
    }


async def test_yes_resolves_the_pending_action_without_the_model(env: Env) -> None:
    action = await env.propose()
    events = await collect(await env.post("Да!"))
    assert types(events) == [
        "RunStarted",
        "TextMessageStart",
        "AgentRouted",
        "ActionResolved",
        "TextMessageContent",
        "TextMessageEnd",
        "RunFinished",
    ]
    assert events[2]["primary"] == "home"
    assert events[3] == {
        "type": "ActionResolved",
        "actionId": str(action.id),
        "status": "applied",
        "message": "Готово.",
    }
    assert env.graph.current.inputs == []
    assert [c[0] for c in env.home.calls] == [Home.APPLY]
    assert env.graph.current.appended == [("[Выключить: Lamp? → applied]", "Готово.")]


async def test_a_longer_reply_goes_to_the_model_and_the_card_stays_pending(env: Env) -> None:
    action = await env.propose()
    env.graph.script([FinalText("Во сколько именно?")])
    await collect(await env.post("да, но в 19:00"))
    assert env.graph.current.inputs == ["да, но в 19:00"]
    assert env.home.calls == []
    async with env.uow.for_user(env.user) as tx:
        assert (await tx.repo(PendingActionRepository).pending(env.user, env.task)).id == action.id  # type: ignore[union-attr]


async def test_statement_pdf_is_imported_by_finance_and_summarized(env: Env) -> None:
    events = await collect(await env.post("", [Upload("s.pdf", "application/pdf", PDF)]))
    assert [c[0] for c in env.finance.calls] == [Finance.IMPORT_STATEMENT]
    assert [a.name for a in env.finance.attachments[0]] == ["s.pdf"]
    assert env.finance.attachments[0][0].data == PDF
    assert [e["primary"] for e in events if e["type"] == "AgentRouted"] == ["finance"]
    assert "Импортировано 12 операций." in text_of(events)
    assert env.graph.current.inputs == []
    user_turn = (await env.messages())[0]
    assert list(user_turn.attachments) == [
        {"kind": "document", "name": "s.pdf", "mime": "application/pdf", "size": len(PDF)}
    ]


async def test_vihealth_pdf_saves_profile_fields(env: Env) -> None:
    await env.lead("body")
    await collect(await env.post("", [Upload("v.pdf", "application/pdf", PDF)]))
    assert [(c[0], c[2]) for c in env.body.calls] == [
        (Body.IMPORT_VIHEALTH, {"save_profile": True})
    ]
    assert env.finance.calls == []


async def test_unknown_pdf_gets_a_hint_and_no_import() -> None:
    env = await opened(build(reader=FakeDocumentReader("Lorem ipsum dolor sit amet")))
    events = await collect(await env.post("", [Upload("x.pdf", "application/pdf", PDF)]))
    assert text_of(events).strip() == TR.t("chat.files.unsupported", "ru", name="x.pdf")
    assert env.finance.calls == []
    assert env.body.calls == []


async def test_photo_is_described_and_never_stored(env: Env) -> None:
    env.graph.script([ToolDone("kitchen"), FinalText("Добавил молоко.")])
    await collect(await env.post("что это?", [Upload("milk.jpg", "image/jpeg", JPEG)]))
    assert [(c[0].name, c[1]) for c in env.vision.calls] == [("milk.jpg", "что это?")]
    assert env.graph.current.inputs == ['что это?\n\n[Photo "milk.jpg": Milk 3.2%]']
    stored = json.dumps(
        [(m.text, list(m.attachments), m.action) for m in await env.messages()],
        ensure_ascii=False,
        default=str,
    )
    assert "SECRET-IMAGE-BYTES" not in stored
    assert list((await env.messages())[0].attachments) == [
        {"kind": "image", "name": "milk.jpg", "mime": "image/jpeg", "size": len(JPEG)}
    ]
    assert env.finance.calls == env.body.calls == env.home.calls == []


async def test_photos_without_a_vision_model_give_run_error() -> None:
    env = await opened(build(vision=FakeImageDescriber(VisionUnavailable())))
    env.graph.script([FinalText("Расскажи словами.")])
    events = await collect(
        await env.post("что это?", [Upload("a.png", "image/png", b"\x89PNG\r\n\x1a\n")])
    )
    assert [e["code"] for e in events if e["type"] == "RunError"] == ["unsupported_attachment"]
    assert env.graph.current.inputs == ["что это?"]
    assert types(events)[-1] == "RunFinished"


async def test_invalid_history_resets_once_and_keeps_the_transcript(env: Env) -> None:
    env.graph.script(InvalidHistory(), [FinalText("Начнём сначала.")])
    events = await collect(await env.post("как я спал?"))
    assert env.graph.current.resets == 1
    assert text_of(events) == TR.t("chat.notices.history_reset", "ru") + "Начнём сначала."
    assert [m.role for m in await env.messages()] == ["user", "assistant"]


async def test_a_graph_crash_is_a_run_error_without_exception_text(env: Env) -> None:
    env.graph.script(RuntimeError("secret detail"))
    events = await collect(await env.post("привет"))
    errors = [e for e in events if e["type"] == "RunError"]
    assert [e["code"] for e in errors] == ["internal"]
    assert errors[0]["message"] == TR.t("chat.errors.internal", "ru")
    assert "secret detail" not in json.dumps(events, ensure_ascii=False)
    assert types(events)[-1] == "RunFinished"


async def test_slow_runs_time_out_with_a_code() -> None:
    env = await opened(build(timeout=0.05))
    env.graph.script([1.0, FinalText("поздно")])
    events = await collect(await env.post("привет"))
    assert [e["code"] for e in events if e["type"] == "RunError"] == ["timeout"]
    assert "поздно" not in text_of(events)


async def test_empty_message_and_busy_task_fail_before_streaming(env: Env) -> None:
    with pytest.raises(EmptyMessage):
        await env.post("   ")
    busy = await opened(build(busy=True))
    with pytest.raises(TaskBusy):
        await busy.post("привет")
    assert await busy.messages() == []


async def test_transcript_matches_stream_on_history_reset_and_documents(env):
    env.graph.script(InvalidHistory(), [FinalText("Answer")])
    events = await collect(await env.post("hello", [Upload("s.pdf", "application/pdf", PDF)]))
    assert (await env.messages())[-1].text == text_of(events)


async def test_documents_are_available_in_checkpoint_history(env):
    events = await collect(await env.post("", [Upload("s.pdf", "application/pdf", PDF)]))
    assert env.graph.current.appended
    assert text_of(events) == env.graph.current.appended[-1][1]


async def test_abandoned_run_releases_lock_and_drops_uploads(env):
    run = await env.post("hello", [Upload("a.jpg", "image/jpeg", JPEG)])
    await run.aclose()
    await run.aclose()
    assert not env.graph.busy
    assert run._uploads == []


async def test_partial_stream_closure_releases_task(env):
    run = await env.post("hello")
    events = run.events()
    await anext(events)
    await events.aclose()
    assert not env.graph.busy


async def test_failed_peer_surfaces_localized_error(env):
    env.graph.script([ToolDone("sleep", failed=True), FinalText("Fallback")])
    events = await collect(await env.post("hello"))
    assert [e["code"] for e in events if e["type"] == "RunError"] == ["agent_unavailable"]


async def test_first_message_sets_title(env):
    await collect(await env.post("hello"))
    async with env.uow.for_user(env.user) as tx:
        assert (await tx.repo(ChatTaskRepository).get(env.user, env.task)).title == "hello"


async def test_document_and_graph_reply_have_consistent_routing(env):
    env.graph.script([ToolDone("sleep"), FinalText("Answer")])
    events = await collect(await env.post("hello", [Upload("s.pdf", "application/pdf", PDF)]))
    last_route = [e["primary"] for e in events if e["type"] == "AgentRouted"][-1]
    assert (await env.messages())[-1].agent == last_route == "sleep"
    assert [e["peers"] for e in events if e["type"] == "AgentConsulted"] == [["finance"]]


async def test_cancelled_run_releases_lock(env):
    import asyncio

    env.graph.script([60.0])
    run = await env.post("hello")
    task = asyncio.create_task(collect(run))
    for _ in range(20):
        if env.graph.current.inputs:
            break
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not env.graph.busy


@pytest.mark.parametrize("stop_at", ["TextMessageContent", "ActionProposed"])
async def test_closing_visible_reply_persists_one_restorable_assistant_turn(env, stop_at):
    action = await env.propose()
    env.graph.script([ToolDone("home", proposal_id=action.id), FinalText("Please confirm.")])
    run = await env.post("Turn off lamp")
    stream = run.events()
    received = []
    async for event in stream:
        received.append(event)
        if event["type"] == stop_at:
            break
    await stream.aclose()
    await run.aclose()
    messages = await env.messages()
    assert len(messages) == 2
    assert messages[-1].text == text_of(received)
    assert messages[-1].action == {
        "id": str(action.id),
        "summary": action.summary,
        "status": "pending",
    }
    assert not env.graph.busy


async def test_cancellation_after_visible_reply_finishes_persistence_before_unlock(
    env, monkeypatch
):
    import asyncio

    action = await env.propose()
    env.graph.script([ToolDone("home", proposal_id=action.id), FinalText("Please confirm."), 60.0])
    run = await env.post("Turn off lamp")
    visible, saving, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    received = []
    async with env.uow.for_user(env.user) as tx:
        transcript = tx.repo(TranscriptRepository)
    append = transcript.append

    async def delayed_append(user, task, message):
        if message.role == "assistant":
            saving.set()
            await release.wait()
        return await append(user, task, message)

    monkeypatch.setattr(transcript, "append", delayed_append)

    async def consume():
        async for event in run.events():
            received.append(event)
            if event["type"] == "TextMessageContent":
                visible.set()

    consuming = asyncio.create_task(consume())
    await asyncio.wait_for(visible.wait(), 1)
    consuming.cancel()
    await asyncio.wait_for(saving.wait(), 1)
    assert env.graph.busy
    consuming.cancel()  # A second disconnect cancellation must not abort the transaction.
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await consuming
    messages = await env.messages()
    assert len(messages) == 2
    assert messages[-1].text == text_of(received)
    assert messages[-1].action["id"] == str(action.id)
    assert not env.graph.busy


async def test_history_reset_restores_document_summary_before_retry(env, monkeypatch):
    session = env.graph.current
    original_run, original_reset = session.run, session.reset
    checkpoint = []
    inputs_at_run = []

    async def append(user_text, assistant_text):
        checkpoint.append((user_text, assistant_text))

    async def reset():
        checkpoint.clear()
        await original_reset()

    async def run(text):
        inputs_at_run.append(list(checkpoint))
        async for event in original_run(text):
            yield event

    monkeypatch.setattr(session, "append", append)
    monkeypatch.setattr(session, "reset", reset)
    monkeypatch.setattr(session, "run", run)
    env.graph.script(InvalidHistory(), [FinalText("Answer")])
    received = await collect(
        await env.post("Summarize this", [Upload("s.pdf", "application/pdf", PDF)])
    )
    assert len(inputs_at_run) == 2
    assert inputs_at_run[0]
    assert inputs_at_run[1] == inputs_at_run[0]
    assert checkpoint == inputs_at_run[0]
    assert (await env.messages())[-1].text == text_of(received)


async def test_nested_graph_finalizer_finishes_before_transcript_and_unlock(env, monkeypatch):
    import asyncio

    order = []

    async def graph_run(text):
        try:
            yield FinalText("Answer")
        finally:
            await asyncio.sleep(0)
            assert env.graph.busy
            order.append("graph_closed")

    async with env.uow.for_user(env.user) as tx:
        transcript = tx.repo(TranscriptRepository)
    append = transcript.append

    async def append_record(user, task, message):
        if message.role == "assistant":
            assert env.graph.busy
            order.append("transcript_saved")
        return await append(user, task, message)

    monkeypatch.setattr(env.graph.current, "run", graph_run)
    monkeypatch.setattr(transcript, "append", append_record)
    run = await env.post("hello")
    stream = run.events()
    async for event in stream:
        if event["type"] == "TextMessageContent":
            break
    await stream.aclose()
    assert order == ["graph_closed", "transcript_saved"]
    assert not env.graph.busy
