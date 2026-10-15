from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from orchestrator.application.ports import (
    ChatTaskRepository,
    NewMessage,
    PendingActionRepository,
    TranscriptRepository,
)
from orchestrator.application.resolve_action import ActionNotFound, ResolveAction
from orchestrator.testing import FakeSession, in_memory_uow
from shared.adapters.i18n import JsonTranslator
from shared.config import find_locales_dir
from shared.ports.skills import SkillCallError, SkillReply, SkillUnavailable
from shared.testing.fakes import FakeSkillClient, FixedClock

NOW = datetime(2026, 10, 14, 18, tzinfo=UTC)
TR = JsonTranslator.from_dir(find_locales_dir())


async def setup(outcome=None):  # type: ignore[no-untyped-def]
    clock = FixedClock(NOW)
    uow = in_memory_uow(clock)
    home = FakeSkillClient(lambda *a: outcome or SkillReply("", {"status": "applied"}))
    resolve = ResolveAction(uow=uow, skills=lambda agent: home, translator=TR, default_locale="ru")
    user = uuid4()
    async with uow.for_user(user) as tx:
        task = await tx.repo(ChatTaskRepository).create(
            user, lead_agent=None, title=None, household_id=None
        )
        action = await tx.repo(PendingActionRepository).propose(
            user,
            task.id,
            agent="home",
            kind="home.call_tool",
            payload={"tool": "HassTurnOff", "args": {"name": "Lamp"}},
            summary="Выключить: Lamp?",
            household_id=None,
            ttl=timedelta(minutes=5),
        )
        await tx.repo(TranscriptRepository).append(
            user,
            task.id,
            NewMessage(
                "assistant",
                "Подтверди",
                agent="home",
                action={"id": str(action.id), "summary": action.summary, "status": "pending"},
            ),
        )
    return resolve, uow, home, clock, user, task.id, action.id


async def test_confirm_applies_once_updates_the_transcript_and_the_checkpoint() -> None:
    resolve, uow, home, _, user, task, action = await setup()
    session = FakeSession()
    first = await resolve(user, task, action, "confirm", session=session)
    second = await resolve(user, task, action, "confirm", session=session)
    assert (first.status, first.message) == ("applied", "Готово.")
    assert (second.status, second.message) == ("applied", "Это уже решено.")
    assert [c[0] for c in home.calls] == ["home.apply_action"]
    assert home.calls[0][2] == {"payload": {"tool": "HassTurnOff", "args": {"name": "Lamp"}}}
    async with uow.for_user(user) as tx:
        messages = await tx.repo(TranscriptRepository).list(user, task)
    assert messages[0].action["status"] == "applied"  # type: ignore[index]
    assert session.appended == [("[Выключить: Lamp? → applied]", "Готово.")]


async def test_reject_never_calls_the_agent() -> None:
    resolve, _, home, _, user, task, action = await setup()
    result = await resolve(user, task, action, "reject", session=FakeSession())
    assert (result.status, result.message) == ("rejected", "Отменено.")
    assert home.calls == []


async def test_expired_is_reported_and_not_applied() -> None:
    resolve, _, home, clock, user, task, action = await setup()
    clock.advance(minutes=6)
    result = await resolve(user, task, action, "confirm", session=FakeSession())
    assert result.status == "expired"
    assert home.calls == []


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (SkillCallError("household_changed"), "household_changed"),
        (SkillUnavailable("down"), "agent_unavailable"),
    ],
)
async def test_agent_failures_are_recorded_with_their_code(error, code) -> None:
    resolve, uow, _, _, user, task, action = await setup(error)
    result = await resolve(user, task, action, "confirm", session=FakeSession())
    assert result.status == "failed"
    assert result.code == code
    assert result.message
    async with uow.for_user(user) as tx:
        again = await tx.repo(PendingActionRepository).claim(user, task, action, "confirm")
    assert again.action is not None
    assert again.action.status == "failed"
    assert again.action.result_code == code


async def test_unknown_or_foreign_actions_are_not_found() -> None:
    resolve, _, _, _, _user, task, action = await setup()
    with pytest.raises(ActionNotFound):
        await resolve(uuid4(), task, action, "confirm", session=FakeSession())


async def test_inflight_claim_is_never_reported_as_applied():
    resolve, uow, home, _, user, task, action = await setup()
    async with uow.for_user(user) as tx:
        await tx.repo(PendingActionRepository).claim(user, task, action, "confirm")
    result = await resolve(user, task, action, "confirm", session=FakeSession())
    assert result.status == "applying"
    assert home.calls == []


async def test_unexpected_failure_is_safe_and_terminal():
    resolve, uow, _, _, user, task, action = await setup(RuntimeError("secret"))
    result = await resolve(user, task, action, "confirm", session=FakeSession())
    assert result.status == "failed"
    assert "secret" not in result.message
    async with uow.for_user(user) as tx:
        claim = await tx.repo(PendingActionRepository).claim(user, task, action, "confirm")
    assert claim.action.status == "failed"
