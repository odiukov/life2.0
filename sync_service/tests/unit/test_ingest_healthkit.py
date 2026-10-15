from datetime import UTC, datetime, timedelta
from uuid import uuid4

from shared.ports.health_logs import HealthLogRepository
from shared.testing.fakes import InMemoryHealthLogs, InMemoryUnitOfWorkFactory
from sync.application.ingest_healthkit import IngestHealthKit
from sync.domain.healthkit import Sample

T = datetime(2026, 10, 13, 22, tzinfo=UTC)


def sample(
    type_: str, start: datetime, value: float, end: datetime | None = None, source: str = "Fitness"
) -> Sample:
    return Sample(type_, start, end, value, None, None, source, None)


async def test_ingest_is_idempotent_and_aggregates_the_touched_days() -> None:
    logs = InMemoryHealthLogs()
    ingest = IngestHealthKit(uow=InMemoryUnitOfWorkFactory({HealthLogRepository: logs}))
    user = uuid4()
    batch = [
        sample("sleepAnalysis", T, 3, T + timedelta(hours=6)),
        sample("stepCount", T - timedelta(hours=10), 5000),
        sample("dietaryEnergyConsumed", T - timedelta(hours=12), 1800),
    ]
    first = await ingest(user, batch)
    second = await ingest(user, batch)
    assert (first.inserted, first.received) == (3, 3)
    assert second.inserted == 0
    assert first.aggregated == {
        "sleep_sessions": 1,
        "daily_stats": 1,
        "workouts": 0,
        "nutrition_days": 1,
    }
    sessions = await logs.recent(user, types=["sleep_session"])
    assert len(sessions) == 1
    assert sessions[0].data["duration_seconds"] == 6 * 3600


async def test_old_days_are_not_reaggregated() -> None:
    logs = InMemoryHealthLogs()
    ingest = IngestHealthKit(uow=InMemoryUnitOfWorkFactory({HealthLogRepository: logs}))
    user = uuid4()
    await ingest(user, [sample("stepCount", T - timedelta(days=30), 100)])
    result = await ingest(user, [sample("stepCount", T, 200)])
    assert result.aggregated["daily_stats"] == 1  # only the touched day, not the one 30 days ago


async def test_boundary_days_keep_complete_totals_and_untouched_days_stay_unchanged() -> None:
    logs = InMemoryHealthLogs()
    ingest = IngestHealthKit(uow=InMemoryUnitOfWorkFactory({HealthLogRepository: logs}))
    user = uuid4()
    day = T.replace(hour=0)
    await ingest(
        user,
        [
            sample("stepCount", day - timedelta(days=2) + timedelta(hours=10), 100),
            sample("stepCount", day - timedelta(days=2) + timedelta(hours=20), 200),
        ],
    )
    await ingest(user, [sample("stepCount", day, 5)])
    totals = await logs.recent(user, types=["daily_stats"])
    assert {r.recorded_at: r.data["stepCount"] for r in totals} == {
        day: 5,
        day - timedelta(days=2): 300,
    }


async def test_reads_historical_chunks_with_an_exclusive_upper_bound() -> None:
    class BoundedLogs(InMemoryHealthLogs):
        async def recent(self, user_id, *, until=None, **kwargs):
            assert until is not None
            return await super().recent(user_id, until=until, **kwargs)

    logs = BoundedLogs()
    ingest = IngestHealthKit(uow=InMemoryUnitOfWorkFactory({HealthLogRepository: logs}))
    await ingest(uuid4(), [sample("stepCount", T, 5)])


async def test_sleep_chunk_reaggregates_the_complete_cross_midnight_night() -> None:
    logs = InMemoryHealthLogs()
    ingest = IngestHealthKit(uow=InMemoryUnitOfWorkFactory({HealthLogRepository: logs}))
    user = uuid4()
    await ingest(user, [sample("sleepAnalysis", T, 3, T + timedelta(hours=2))])
    await ingest(user, [sample("sleepAnalysis", T + timedelta(hours=2), 4, T + timedelta(hours=4))])
    rows = await logs.recent(user, types=["sleep_session"])
    assert len(rows) == 1
    assert rows[0].data["duration_seconds"] == 4 * 3600


async def test_changed_duplicate_keeps_original_raw_value_and_count() -> None:
    logs = InMemoryHealthLogs()
    ingest = IngestHealthKit(uow=InMemoryUnitOfWorkFactory({HealthLogRepository: logs}))
    user = uuid4()
    await ingest(user, [sample("stepCount", T, 100)])
    result = await ingest(user, [sample("stepCount", T, 200)])
    assert result.inserted == 0
    rows = await logs.recent(user, types=["stepCount", "daily_stats"])
    assert {r.type: r.data for r in rows} == {
        "stepCount": {"value": 100},
        "daily_stats": {"stepCount": 100},
    }
