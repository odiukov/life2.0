from datetime import UTC, datetime
from uuid import uuid4

from gateway.hooks import HouseholdEnsurer
from household.application.service import HouseholdService
from household.testing import InMemoryHouseholds, in_memory_uow
from shared.testing.fakes import FixedClock

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


async def test_ensures_once_per_user() -> None:
    repo = InMemoryHouseholds(FixedClock(NOW))
    calls: list[object] = []
    svc = HouseholdService(in_memory_uow(repo), FixedClock(NOW))
    original = svc.ensure

    async def counting(user_id):  # type: ignore[no-untyped-def]
        calls.append(user_id)
        return await original(user_id)

    svc.ensure = counting  # type: ignore[method-assign]
    hook = HouseholdEnsurer(svc)
    user = uuid4()
    await hook(user)
    await hook(user)
    assert calls == [user]
    assert len(repo.households) == 1


async def test_failures_are_swallowed_and_retried_next_time() -> None:
    class Broken:
        attempts = 0

        async def ensure(self, user_id):  # type: ignore[no-untyped-def]
            self.attempts += 1
            raise RuntimeError("db down")

    broken = Broken()
    hook = HouseholdEnsurer(broken)  # type: ignore[arg-type]
    user = uuid4()
    await hook(user)
    await hook(user)
    assert broken.attempts == 2


async def test_simultaneous_first_requests_wait_for_one_ensure() -> None:
    import asyncio
    from uuid import UUID

    started = asyncio.Event()
    release = asyncio.Event()
    finished: list[UUID] = []
    calls: list[UUID] = []

    class Blocking:
        async def ensure(self, user_id: UUID) -> UUID:
            calls.append(user_id)
            started.set()
            await release.wait()
            finished.append(user_id)
            return user_id

    hook = HouseholdEnsurer(Blocking())
    user = uuid4()
    first = asyncio.create_task(hook(user))
    await started.wait()
    second = asyncio.create_task(hook(user))
    await asyncio.sleep(0)
    assert not second.done()
    release.set()
    await asyncio.gather(first, second)
    assert calls == [user]
    assert finished == [user]
