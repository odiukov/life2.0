from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from shared.testing.fakes import FixedClock
from sync.application.ports import AuthFailed
from sync.application.sync_user import Preview, SyncUser
from sync.domain.garmin import GarminBundle
from sync.testing import FakeGarminClient, MemoryBackend
from sync_fixtures import ACTIVITY, STATS

USER = uuid4()


def build(garmin: FakeGarminClient) -> tuple[MemoryBackend, SyncUser]:
    backend = MemoryBackend()
    backend.users.seed(USER, timezone="Europe/Lisbon")
    backend.credentials.rows[(USER, "garmin")] = {"email": "a@b.c", "password": "pw"}
    sync = SyncUser(
        uow=backend.uow,
        garmin=garmin,
        yazio=None,
        clock=FixedClock(datetime(2026, 10, 13, 8, tzinfo=UTC)),
        cooldown=timedelta(minutes=10),
    )
    return backend, sync


async def test_preview_counts_rows_and_writes_nothing() -> None:
    garmin = FakeGarminClient(
        GarminBundle(
            activities=(ACTIVITY,),
            stats=((date(2026, 10, 13), STATS),),
            failures=("hrv 2026-10-12",),
        ),
        token='{"new": 1}',
    )
    backend, sync = build(garmin)
    assert await sync.preview(USER, "garmin") == Preview(
        "partial", {"activity": 1, "daily_stats": 1}, ("hrv 2026-10-12",)
    )
    assert USER not in backend.logs.rows
    assert backend.state.rows == {}
    assert "garmin_token" not in backend.credentials.rows[(USER, "garmin")]
    assert (await sync(USER, ["garmin"]))[0].status == "partial"


async def test_preview_reports_codes() -> None:
    _, sync = build(FakeGarminClient(error=AuthFailed()))
    assert await sync.preview(USER, "garmin") == Preview("auth_failed", {}, ())
    _, sync = build(FakeGarminClient())
    assert await sync.preview(USER, "yazio") == Preview("disabled", {}, ())


async def test_preview_missing_and_unreadable_credentials() -> None:
    backend, sync = build(FakeGarminClient())
    del backend.credentials.rows[(USER, "garmin")]
    assert await sync.preview(USER, "garmin") == Preview("not_connected", {}, ())
    backend.credentials.unreadable.add((USER, "garmin"))
    assert await sync.preview(USER, "garmin") == Preview("auth_failed", {}, ())
