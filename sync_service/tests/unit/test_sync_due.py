from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from shared.testing.fakes import FixedClock
from structlog.testing import capture_logs
from sync.application.ports import AuthFailed, Unavailable
from sync.application.sync_due import DueReport, SyncDue
from sync.application.sync_user import SyncUser
from sync.domain.garmin import GarminBundle
from sync.testing import FakeGarminClient, MemoryBackend
from sync_fixtures import STATS

LISBON_0905 = datetime(2026, 10, 13, 8, 5, tzinfo=UTC)
CREDS = {"email": "a@b.c", "password": "pw"}


def setup(
    garmin: FakeGarminClient, *, users: int = 1, tz: str = "Europe/Lisbon"
) -> tuple[MemoryBackend, FixedClock, SyncDue, list]:
    backend, clock = MemoryBackend(), FixedClock(LISBON_0905)
    ids = [uuid4() for _ in range(users)]
    for user in ids:
        backend.users.seed(user, timezone=tz)
        backend.credentials.rows[(user, "garmin")] = dict(CREDS)
    sync_user = SyncUser(
        uow=backend.uow, garmin=garmin, yazio=None, clock=clock, cooldown=timedelta(minutes=10)
    )
    return backend, clock, SyncDue(uow=backend.uow, sync_user=sync_user, clock=clock, hour=9), ids


async def test_due_at_0905_local_syncs_once_and_a_second_run_does_nothing() -> None:
    garmin = FakeGarminClient(GarminBundle(stats=((date(2026, 10, 13), STATS),)))
    backend, clock, due, [user] = setup(garmin)
    assert await due() == DueReport(users=1, failed=0)
    clock.advance(minutes=15)
    assert await due() == DueReport(users=0, failed=0)
    assert len(garmin.calls) == 1
    assert len(backend.logs.rows[user]) == 1


async def test_nobody_is_due_before_the_local_hour() -> None:
    garmin = FakeGarminClient()
    _, clock, due, _ = setup(garmin, tz="America/New_York")  # 04:05 there
    assert await due() == DueReport(0, 0)
    clock.set(datetime(2026, 10, 13, 13, 0, tzinfo=UTC))  # 09:00 New York
    assert await due() == DueReport(1, 0)


async def test_auth_failure_is_not_retried_until_tomorrow() -> None:
    garmin = FakeGarminClient(error=AuthFailed())
    backend, clock, due, [user] = setup(garmin)
    tries = 0
    original = garmin.fetch

    async def counting(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal tries
        tries += 1
        return await original(*args, **kwargs)

    garmin.fetch = counting  # type: ignore[method-assign]
    for _ in range(15):  # every hour until 23:05 local
        await due()
        clock.advance(hours=1)
    assert tries == 1
    assert backend.state.rows[(user, "garmin")].last_error == "auth_failed"
    clock.set(datetime(2026, 10, 14, 8, 5, tzinfo=UTC))  # 09:05 next day
    await due()
    assert tries == 2


async def test_unavailable_is_retried_after_an_hour() -> None:
    garmin = FakeGarminClient(error=Unavailable())
    _backend, clock, due, [_user] = setup(garmin)
    await due()
    clock.advance(minutes=45)
    assert await due() == DueReport(0, 0)
    clock.advance(minutes=15)
    assert await due() == DueReport(1, 0)


async def test_one_users_crash_does_not_stop_the_others() -> None:
    class Flaky(FakeGarminClient):
        async def fetch(self, days, credentials, token):  # type: ignore[no-untyped-def]
            if credentials.email == "boom@b.c":
                raise RuntimeError("secret detail boom@b.c")
            return await super().fetch(days, credentials, token)

    garmin = Flaky()
    backend, _, due, [a, _b] = setup(garmin, users=2)
    original_sync = due._sync_user

    class CrashingSyncUser(SyncUser):
        async def __call__(self, user_id, services):  # type: ignore[no-untyped-def]
            if user_id == a:
                raise RuntimeError("secret detail boom@b.c")
            return await original_sync(user_id, services)

    due._sync_user = CrashingSyncUser(
        uow=backend.uow,
        garmin=garmin,
        yazio=None,
        clock=FixedClock(LISBON_0905),
        cooldown=timedelta(minutes=10),
    )
    with capture_logs() as logs:
        assert await due() == DueReport(users=2, failed=1)
    assert [call[1].email for call in garmin.calls] == ["a@b.c"]
    crash = next(e for e in logs if e["event"] == "sync_user_crashed")
    assert crash == {
        "event": "sync_user_crashed",
        "log_level": "warning",
        "user_id": str(a),
        "code": "unexpected",
    }
    assert "boom" not in repr(logs)


async def test_force_ignores_only_the_hour() -> None:
    garmin = FakeGarminClient()
    _, _, due, _ = setup(garmin, tz="America/New_York")
    assert await due(force=True) == DueReport(1, 0)
    assert await due(force=True) == DueReport(0, 0)  # synced today: still not due


async def test_reseal_is_idempotent_and_keeps_unreadable_rows() -> None:
    from sync.application.reseal import ResealReport, reseal_plaintext

    backend = MemoryBackend()
    readable, unreadable = uuid4(), uuid4()
    backend.credentials.rows[(readable, "ha")] = {"token": "secret"}
    backend.credentials.rows[(unreadable, "garmin")] = dict(CREDS)
    backend.credentials.plaintext.update({(readable, "ha"), (unreadable, "garmin")})
    backend.credentials.unreadable.add((unreadable, "garmin"))
    assert await reseal_plaintext(backend.uow) == ResealReport(1, 1)
    assert await reseal_plaintext(backend.uow) == ResealReport(0, 1)
