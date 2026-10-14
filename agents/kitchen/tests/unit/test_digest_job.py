import asyncio
from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from kitchen.application.digest_job import SendDueDigests
from kitchen.application.ports import DigestRuns, DueDigest, DueDigests, HouseholdContext
from kitchen.testing import (
    FakeDueDigests,
    InMemoryDigestRuns,
    KitchenMemory,
    in_memory_uow,
    make_batch,
)
from shared.adapters.i18n import JsonTranslator
from shared.config import find_locales_dir
from shared.testing.fakes import FakeNotificationSender, FixedClock

NOW = datetime(2026, 10, 13, 18, 5, tzinfo=UTC)
A, B = UUID(int=1), UUID(int=2)
HOME = UUID(int=9)
DUE = DueDigest(HOME, A, (A, B), "Europe/London", date(2026, 10, 13))


def env(batches, runs=None, clock=None):  # type: ignore[no-untyped-def]
    memory = KitchenMemory(HouseholdContext(HOME, "Europe/London", {A: "Аня", B: "Боря"}))
    for batch in batches:
        memory.batches.rows[batch.pk] = batch
    memory.locales.locales[B] = "en"
    runs, due = runs or InMemoryDigestRuns(), FakeDueDigests([DUE])
    memory.extra.update({DigestRuns: runs, DueDigests: due})
    sender = FakeNotificationSender()
    job = SendDueDigests(
        in_memory_uow(memory),
        sender,
        JsonTranslator.from_dir(find_locales_dir()),
        clock or FixedClock(NOW),
        default_locale="ru",
    )
    return job, sender, runs, due, memory


async def test_sends_localized_digest_once() -> None:
    job, sender, runs, _, _ = env(
        [
            make_batch(id=1, display_name="курица", expires_on=date(2026, 10, 14)),
            make_batch(id=2, display_name="йогурт", expires_on=date(2026, 10, 13)),
            make_batch(id=3, display_name="кефир", expires_on=date(2026, 10, 12)),
            make_batch(id=4, display_name="сыр", expires_on=date(2026, 10, 14)),
            make_batch(
                id=5,
                display_name="рис",
                expires_on=date(2026, 12, 1),
                next_check_on=date(2026, 12, 1),
            ),
        ]
    )
    assert await job() == 1
    by_user = dict(sender.sent)
    assert by_user[A].title == "Пора проверить продукты"
    assert (
        by_user[A].body == "кефир (просрочено), йогурт (сегодня), курица (завтра), и ещё 1 продукт"
    )
    assert by_user[B].title == "Time to check the food"
    assert by_user[A].data == {"route": "/kitchen"}
    assert runs.claimed == {(HOME, date(2026, 10, 13))}
    assert await job() == 0
    assert len(sender.sent) == 2


async def test_empty_digest_claims_but_sends_nothing() -> None:
    job, sender, runs, _, _ = env(
        [make_batch(id=1, expires_on=date(2026, 12, 1), next_check_on=date(2026, 12, 1))]
    )
    assert await job() == 0
    assert sender.sent == []
    assert runs.claimed == {(HOME, date(2026, 10, 13))}


async def test_stale_membership_does_not_leak_inventory() -> None:
    job, sender, runs, _, memory = env([make_batch(id=1, expires_on=date(2026, 10, 13))])
    memory.context = HouseholdContext(
        UUID(int=10), "Europe/London", {A: "Аня", UUID(int=3): "Вера"}
    )
    assert await job() == 0
    assert sender.sent == []
    assert runs.claimed == set()


async def test_stale_recipient_snapshot_does_not_send() -> None:
    job, sender, runs, _, memory = env([make_batch(id=1, expires_on=date(2026, 10, 13))])
    memory.context = HouseholdContext(HOME, "Europe/London", {A: "Аня", UUID(int=3): "Вера"})
    assert await job() == 0
    assert sender.sent == []
    assert runs.claimed == set()


async def test_member_departure_after_claim_prevents_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job, sender, runs, _, memory = env([make_batch(id=1, expires_on=date(2026, 10, 13))])
    original = memory.locales.locale

    async def leave_after_claim(user_id: UUID) -> str | None:
        memory.context = HouseholdContext(HOME, "Europe/London", {A: "Аня"})
        return await original(user_id)

    monkeypatch.setattr(memory.locales, "locale", leave_after_claim)
    assert await job() == 0
    assert sender.sent == []
    assert runs.claimed == {(HOME, date(2026, 10, 13))}


@pytest.mark.parametrize("advance_on_lock", [1, 2])
async def test_midnight_during_household_lock_skips_stale_digest(
    monkeypatch: pytest.MonkeyPatch, advance_on_lock: int
) -> None:
    clock = FixedClock(NOW)
    job, sender, runs, _, memory = env(
        [make_batch(id=1, expires_on=date(2026, 10, 13))], clock=clock
    )
    acquired = asyncio.Event()
    release = asyncio.Event()
    original_lock = memory.batches.lock
    calls = 0

    async def blocking_lock() -> None:
        nonlocal calls
        calls += 1
        if calls == advance_on_lock:
            acquired.set()
            await release.wait()
            clock.set(datetime(2026, 10, 13, 23, 1, tzinfo=UTC))  # Oct 14 in London.
        await original_lock()

    monkeypatch.setattr(memory.batches, "lock", blocking_lock)
    pending = asyncio.create_task(job())
    await asyncio.wait_for(acquired.wait(), timeout=2)
    release.set()
    assert await pending == 0
    assert sender.sent == []
    assert runs.claimed == (set() if advance_on_lock == 1 else {(HOME, date(2026, 10, 13))})


async def test_failure_in_one_household_does_not_stop_others() -> None:
    broken = UUID(int=77)
    job, sender, _, due, _ = env(
        [make_batch(id=1, expires_on=date(2026, 10, 13))], InMemoryDigestRuns(fail_for={broken})
    )
    due.items.insert(
        0, DueDigest(broken, UUID(int=78), (UUID(int=78),), "Europe/London", date(2026, 10, 13))
    )
    assert await job() == 1
    assert {user for user, _ in sender.sent} == {A, B}
