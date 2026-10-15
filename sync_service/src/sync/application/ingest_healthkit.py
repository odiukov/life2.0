from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC
from uuid import UUID

from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.uow import UnitOfWorkFactory

from sync.application.sync_user import to_health_log
from sync.domain.healthkit import (
    RAW_TYPES,
    Sample,
    daily_rows,
    night_of,
    nutrition_rows,
    raw_row,
    sleep_rows,
    touched_window,
    workout_rows,
)
from sync.domain.rows import Row


def _row(r: HealthLogRow) -> Row:
    return Row(agent=r.agent, type=r.type, source=r.source, recorded_at=r.recorded_at, data=r.data)


@dataclass(frozen=True, slots=True)
class HealthKitResult:
    inserted: int
    received: int
    aggregated: dict[str, int] = field(default_factory=dict)


class IngestHealthKit:
    def __init__(self, *, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    async def __call__(self, user_id: UUID, samples: Sequence[Sample]) -> HealthKitResult:
        if not samples:
            return HealthKitResult(
                0, 0, {"sleep_sessions": 0, "daily_stats": 0, "workouts": 0, "nutrition_days": 0}
            )
        async with self._uow.for_user(user_id) as tx:
            logs = tx.repo(HealthLogRepository)
            await logs.lock_user(user_id)
            inserted = 0
            for sample in samples:
                inserted += await logs.insert_once(user_id, to_health_log(raw_row(sample)))
            aggregates: dict[tuple[str, str, object], tuple[str, Row]] = {}
            days = {sample.start.astimezone(UTC).date() for sample in samples}
            for day in sorted(days):
                batch = [sample for sample in samples if sample.start.astimezone(UTC).date() == day]
                start, end = touched_window(batch)
                raw = sorted(
                    (
                        _row(r)
                        for r in await logs.recent(
                            user_id, types=list(RAW_TYPES), since=start, until=end
                        )
                    ),
                    key=lambda row: row.recorded_at,
                )
                nights = {night_of(sample.start) for sample in batch}
                for name, rows in (
                    ("sleep_sessions", sleep_rows(raw)),
                    ("daily_stats", daily_rows(raw)),
                    ("workouts", workout_rows(raw)),
                    ("nutrition_days", nutrition_rows(raw)),
                ):
                    for row in rows:
                        key_day = row.recorded_at.astimezone(UTC).date()
                        if key_day not in (nights if name == "sleep_sessions" else {day}):
                            continue
                        aggregates[row.source, row.type, row.recorded_at] = name, row
            counts = {"sleep_sessions": 0, "daily_stats": 0, "workouts": 0, "nutrition_days": 0}
            for name, row in aggregates.values():
                await logs.upsert(user_id, to_health_log(row))
                counts[name] += 1
        return HealthKitResult(inserted, len(samples), counts)
