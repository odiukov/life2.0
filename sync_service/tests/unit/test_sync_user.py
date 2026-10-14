from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from shared.testing.fakes import FixedClock
from structlog.testing import capture_logs
from sync.application.ports import AuthFailed, RateLimited
from sync.application.sync_user import ServiceResult, SyncUser
from sync.domain.garmin import GarminBundle
from sync.domain.yazio import YazioBundle, YazioItem
from sync.testing import FakeGarminClient, FakeYazioClient, MemoryBackend
from sync_fixtures import ACTIVITY, STATS

NOW = datetime(2026, 10, 13, 8, 30, tzinfo=UTC)  # 09:30 in Lisbon
USER = uuid4()
GARMIN = {"email": "person@example.com", "password": "hunter2", "garmin_token": '{"old": 1}'}
YAZIO = {"email": "person@example.com", "password": "hunter2"}


def build(
    backend: MemoryBackend,
    *,
    garmin: FakeGarminClient | None = None,
    yazio: FakeYazioClient | None = None,
    clock: FixedClock | None = None,
) -> SyncUser:
    return SyncUser(
        uow=backend.uow,
        garmin=garmin,
        yazio=yazio,
        clock=clock or FixedClock(NOW),
        cooldown=timedelta(minutes=10),
    )


@pytest.fixture
def backend() -> MemoryBackend:
    backend = MemoryBackend()
    backend.users.seed(USER, timezone="Europe/Lisbon")
    backend.credentials.rows[(USER, "garmin")] = dict(GARMIN)
    backend.credentials.rows[(USER, "yazio")] = dict(YAZIO)
    return backend


async def test_syncs_both_services_in_the_users_window(backend: MemoryBackend) -> None:
    garmin = FakeGarminClient(
        GarminBundle(activities=(ACTIVITY,), stats=((date(2026, 10, 13), STATS),)),
        token='{"new": 1}',
    )
    yazio = FakeYazioClient(
        YazioBundle(days=((date(2026, 10, 13), (YazioItem("lunch", "x", 1, 500, 1, 1, 1),)),))
    )
    results = await build(backend, garmin=garmin, yazio=yazio)(USER)
    assert results == [
        ServiceResult("garmin", "ok", written=2),
        ServiceResult("yazio", "ok", written=1),
    ]
    assert garmin.calls[0][0] == [date(2026, 10, 13) - timedelta(days=i) for i in range(7)]
    assert garmin.calls[0][1].email == "person@example.com"
    assert garmin.calls[0][2] == '{"old": 1}'
    assert yazio.calls[0][0] == [date(2026, 10, 13), date(2026, 10, 12)]
    assert backend.credentials.rows[(USER, "garmin")]["garmin_token"] == '{"new": 1}'
    assert {r.type for r in backend.logs.rows[USER]} == {"activity", "daily_stats", "meal"}
    status = backend.state.rows[(USER, "garmin")]
    assert (status.last_success_at, status.last_error) == (NOW, None)


async def test_window_starts_at_the_users_local_today(backend: MemoryBackend) -> None:
    backend.users.seed(USER, timezone="Pacific/Auckland")  # 21:30 on the 13th there
    garmin = FakeGarminClient(GarminBundle())
    await build(
        backend, garmin=garmin, clock=FixedClock(datetime(2026, 10, 13, 8, 30, tzinfo=UTC))
    )(USER, ["garmin"])
    assert garmin.calls[0][0][0] == date(2026, 10, 13)
    await build(
        backend, garmin=garmin, clock=FixedClock(datetime(2026, 10, 13, 11, 30, tzinfo=UTC))
    )(USER, ["garmin"])
    assert garmin.calls[1][0][0] == date(2026, 10, 14)  # already the 14th in Auckland


async def test_a_second_run_inside_the_cooldown_is_already_fresh(backend: MemoryBackend) -> None:
    clock = FixedClock(NOW)
    garmin = FakeGarminClient(GarminBundle())
    sync = build(backend, garmin=garmin, clock=clock)
    assert (await sync(USER, ["garmin"]))[0].status == "ok"
    clock.advance(minutes=9)
    assert await sync(USER, ["garmin"]) == [ServiceResult("garmin", "already_fresh")]
    clock.advance(minutes=2)
    assert (await sync(USER, ["garmin"]))[0].status == "ok"
    assert len(garmin.calls) == 2


async def test_rows_are_upserted_so_a_rerun_reports_unchanged(backend: MemoryBackend) -> None:
    clock = FixedClock(NOW)
    garmin = FakeGarminClient(GarminBundle(activities=(ACTIVITY,)))
    sync = build(backend, garmin=garmin, clock=clock)
    await sync(USER, ["garmin"])
    clock.advance(minutes=11)
    assert await sync(USER, ["garmin"]) == [ServiceResult("garmin", "ok", written=0, unchanged=1)]
    assert len(backend.logs.rows[USER]) == 1


async def test_refreshed_token_is_saved_even_if_rows_fail(backend: MemoryBackend) -> None:
    backend.logs.fail_upserts = True
    garmin = FakeGarminClient(GarminBundle(activities=(ACTIVITY,)), token='{"refreshed": 1}')
    with capture_logs() as logs:
        results = await build(backend, garmin=garmin)(USER, ["garmin"])
    assert results == [ServiceResult("garmin", "unavailable")]
    assert backend.credentials.rows[(USER, "garmin")]["garmin_token"] == '{"refreshed": 1}'
    assert backend.state.rows[(USER, "garmin")].last_error == "unavailable"
    assert backend.state.rows[(USER, "garmin")].last_success_at is None
    assert [e["event"] for e in logs] == ["sync_failed"]
    assert set(logs[0]) <= {"event", "log_level", "code", "service", "user_id"}


async def test_partial_fetch_counts_as_success_with_a_marker(backend: MemoryBackend) -> None:
    garmin = FakeGarminClient(GarminBundle(activities=(ACTIVITY,), failures=("hrv 2026-10-12",)))
    assert await build(backend, garmin=garmin)(USER, ["garmin"]) == [
        ServiceResult("garmin", "partial", written=1)
    ]
    status = backend.state.rows[(USER, "garmin")]
    assert (status.last_success_at, status.last_error) == (NOW, "partial")


@pytest.mark.parametrize(
    ("error", "code"), [(AuthFailed(), "auth_failed"), (RateLimited(), "rate_limited")]
)
async def test_provider_errors_are_recorded_and_logged_without_details(
    backend: MemoryBackend, error: Exception, code: str
) -> None:
    with capture_logs() as logs:
        results = await build(backend, garmin=FakeGarminClient(error=error))(USER, ["garmin"])
    assert results == [ServiceResult("garmin", code)]  # type: ignore[arg-type]
    assert backend.state.rows[(USER, "garmin")].last_error == code
    assert logs == [
        {
            "event": "sync_failed",
            "log_level": "warning",
            "code": code,
            "service": "garmin",
            "user_id": str(USER),
        }
    ]
    assert backend.credentials.rows[(USER, "garmin")]["garmin_token"] == '{"old": 1}'  # untouched


async def test_unreadable_or_incomplete_credentials_are_auth_failed(backend: MemoryBackend) -> None:
    backend.credentials.unreadable.add((USER, "garmin"))
    backend.credentials.rows[(USER, "yazio")] = {"email": "person@example.com"}  # no password
    garmin, yazio = FakeGarminClient(), FakeYazioClient()
    results = await build(backend, garmin=garmin, yazio=yazio)(USER)
    assert results == [
        ServiceResult("garmin", "auth_failed"),
        ServiceResult("yazio", "auth_failed"),
    ]
    assert garmin.calls == []
    assert yazio.calls == []
    assert backend.state.rows[(USER, "garmin")].last_attempt_at == NOW


async def test_missing_integration_and_disabled_client(backend: MemoryBackend) -> None:
    del backend.credentials.rows[(USER, "yazio")]
    results = await build(backend, garmin=FakeGarminClient(), yazio=FakeYazioClient())(
        USER, ["yazio"]
    )
    assert results == [ServiceResult("yazio", "not_connected")]
    assert await build(backend, garmin=FakeGarminClient(), yazio=None)(USER, ["yazio"]) == [
        ServiceResult("yazio", "disabled")
    ]
    assert (USER, "yazio") not in backend.state.rows


async def test_one_failing_service_does_not_stop_the_other(backend: MemoryBackend) -> None:
    yazio = FakeYazioClient(
        YazioBundle(days=((date(2026, 10, 13), (YazioItem("lunch", "x", 1, 500, 1, 1, 1),)),))
    )
    results = await build(backend, garmin=FakeGarminClient(error=AuthFailed()), yazio=yazio)(USER)
    assert [r.status for r in results] == ["auth_failed", "ok"]


async def test_an_unchanged_token_is_not_rewritten(backend: MemoryBackend) -> None:
    garmin = FakeGarminClient(GarminBundle(), token='{"old": 1}')
    await build(backend, garmin=garmin)(USER, ["garmin"])
    assert backend.credentials.merges == []


async def test_failure_hooks_are_preserved_by_tenant_binding(backend: MemoryBackend) -> None:
    garmin = FakeGarminClient(token='{"new": 1}')
    await build(backend, garmin=garmin)(USER, ["garmin"])
    assert backend.credentials.merges == [(USER, "garmin", {"garmin_token": '{"new": 1}'})]


async def test_unexpected_provider_failure_is_isolated_and_private(backend: MemoryBackend) -> None:
    with capture_logs() as logs:
        results = await build(
            backend, garmin=FakeGarminClient(error=RuntimeError("secret")), yazio=FakeYazioClient()
        )(USER)
    assert [r.status for r in results] == ["unavailable", "ok"]
    assert all(set(entry) <= {"event", "log_level", "code", "service", "user_id"} for entry in logs)
    assert "secret" not in str(logs)


async def test_invalid_credentials_still_honour_cooldown(backend: MemoryBackend) -> None:
    backend.credentials.unreadable.add((USER, "garmin"))
    sync = build(backend, garmin=FakeGarminClient())
    assert (await sync(USER, ["garmin"]))[0].status == "auth_failed"
    assert (await sync(USER, ["garmin"]))[0].status == "already_fresh"


@pytest.mark.parametrize(
    "replacement", [None, GARMIN, {"email": "new@example.com", "password": "new"}]
)
@pytest.mark.parametrize("token", [None, '{"old": 1}', '{"refreshed": 1}'])
async def test_reconnect_during_fetch_discards_obsolete_results(backend, replacement, token):
    class ReconnectingGarmin(FakeGarminClient):
        async def fetch(self, days, credentials, stored):
            # Deterministic interleaving while the provider request is in flight.
            if replacement is None:
                await backend.credentials.delete(USER, "garmin")
            else:
                await backend.credentials.put(USER, "garmin", replacement)
            return GarminBundle(activities=(ACTIVITY,)), token

    result = await build(backend, garmin=ReconnectingGarmin())(USER, ["garmin"])
    assert result == [ServiceResult("garmin", "unavailable")]
    assert await backend.credentials.get(USER, "garmin") == replacement
    assert not backend.logs.rows.get(USER)
    assert backend.state.rows[(USER, "garmin")].last_success_at is None


async def test_reconnect_between_token_and_rows_discards_obsolete_results(backend):
    from contextlib import asynccontextmanager

    original_uow = backend.uow
    replacement = {"email": "new@example.com", "password": "new"}

    class ReconnectingUnitOfWork:
        calls = 0

        @asynccontextmanager
        async def for_user(self, user_id):
            self.calls += 1
            if self.calls == 3:
                assert (
                    backend.credentials.rows[(USER, "garmin")]["garmin_token"] == '{"refreshed": 1}'
                )
                await backend.credentials.put(USER, "garmin", replacement)
            async with original_uow.for_user(user_id) as tx:
                yield tx

    backend.uow = ReconnectingUnitOfWork()
    result = await build(
        backend,
        garmin=FakeGarminClient(GarminBundle(activities=(ACTIVITY,)), token='{"refreshed": 1}'),
    )(USER, ["garmin"])
    assert result == [ServiceResult("garmin", "unavailable")]
    assert await backend.credentials.get(USER, "garmin") == replacement
    assert not backend.logs.rows.get(USER)
    assert backend.state.rows[(USER, "garmin")].last_success_at is None
