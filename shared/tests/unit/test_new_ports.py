from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from shared.ports.llm import LLMTask
from shared.ports.notifications import Notification
from shared.ports.stt import AudioTooLong, Transcript
from shared.testing.fakes import (
    FakeNotificationSender,
    FakeScheduler,
    FakeSpeechToText,
    InMemoryNotificationInbox,
    InMemoryPushTokens,
)

T0 = datetime(2026, 10, 14, 18, 0, tzinfo=UTC)
N = Notification(kind="kitchen.digest", title="t", body="b", data={"route": "/kitchen"})


def test_kitchen_llm_tasks_exist() -> None:
    assert LLMTask("kitchen_extract") is LLMTask.KITCHEN_EXTRACT
    assert LLMTask("kitchen_query") is LLMTask.KITCHEN_QUERY


async def test_fake_stt_returns_scripted_transcript_and_records_calls() -> None:
    stt = FakeSpeechToText(Transcript("купил хлеб", "ru", 1.5))
    got = await stt.transcribe(b"abc", mime="audio/m4a", language="ru")
    assert got == Transcript("купил хлеб", "ru", 1.5)
    assert stt.calls == [(3, "audio/m4a", "ru")]


async def test_fake_stt_can_raise() -> None:
    stt = FakeSpeechToText(error=AudioTooLong("61s"))
    with pytest.raises(AudioTooLong):
        await stt.transcribe(b"x", mime="audio/wav", language=None)


async def test_fake_scheduler_records_interval_jobs() -> None:
    ran: list[int] = []

    async def job() -> None:
        ran.append(1)

    scheduler = FakeScheduler()
    scheduler.add_interval("digest", job, minutes=15)
    assert scheduler.intervals == {"digest": 15}
    await scheduler.run("digest")
    assert ran == [1]


async def test_fake_sender_records_per_recipient() -> None:
    sender = FakeNotificationSender()
    a, b = uuid4(), uuid4()
    await sender.send([a, b], N)
    assert sender.sent == [(a, N), (b, N)]


async def test_inbox_pages_newest_first_and_counts_unread() -> None:
    inbox = InMemoryNotificationInbox()
    user = uuid4()
    first = await inbox.add(user, N, created_at=T0)
    second = await inbox.add(user, N, created_at=T0 + timedelta(minutes=1))
    page = await inbox.page(user, before=None, limit=10)
    assert [i.id for i in page] == [second, first]
    assert await inbox.unread_count(user) == 2
    assert await inbox.mark_read(user, first, at=T0) is True
    assert await inbox.mark_read(user, uuid4(), at=T0) is False
    assert await inbox.unread_count(user) == 1
    assert await inbox.mark_all_read(user, at=T0) == 1
    older = await inbox.page(user, before=T0 + timedelta(minutes=1), limit=10)
    assert [i.id for i in older] == [first]
    assert await inbox.page(uuid4(), before=None, limit=10) == []


async def test_push_tokens_upsert_is_idempotent_and_scoped() -> None:
    tokens = InMemoryPushTokens()
    a, b = uuid4(), uuid4()
    await tokens.upsert(a, "ExponentPushToken[1]", "ios", at=T0)
    await tokens.upsert(a, "ExponentPushToken[1]", "ios", at=T0 + timedelta(days=1))
    await tokens.upsert(b, "ExponentPushToken[2]", "ios", at=T0)
    assert await tokens.for_user(a) == ["ExponentPushToken[1]"]
    await tokens.delete(a, "ExponentPushToken[2]")  # not a's token: no effect
    assert await tokens.for_user(b) == ["ExponentPushToken[2]"]
    await tokens.delete(b, "ExponentPushToken[2]")
    assert await tokens.for_user(b) == []
