"""Helpers for the structured dashboard skills every health agent serves (no LLM).

Windows are computed from the clock and the user's zone, never from the database clock.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from shared.a2a.executor import SkillResult
from shared.a2a.request import SkillRequest
from shared.ports.clock import Clock
from shared.ports.uow import UnitOfWork, UnitOfWorkFactory
from shared.ports.users import UserSettings, UserSettingsRepository


@dataclass(frozen=True, slots=True)
class DashboardContext:
    user_id: UUID
    settings: UserSettings
    now: datetime

    @property
    def zone(self) -> ZoneInfo:
        return self.settings.timezone

    @property
    def today(self) -> date:
        return self.settings.today(self.now)

    @property
    def yesterday(self) -> date:
        return self.today - timedelta(days=1)

    def bounds(self, day: date) -> tuple[datetime, datetime]:
        return (
            datetime.combine(day, time.min, tzinfo=self.zone).astimezone(UTC),
            datetime.combine(day + timedelta(days=1), time.min, tzinfo=self.zone).astimezone(UTC),
        )

    def local_date(self, ts: datetime) -> date:
        return ts.astimezone(self.zone).date()

    def last_days(self, n: int) -> list[date]:
        return [self.today - timedelta(days=n - 1 - i) for i in range(n)]


def pg_round(value: float | Decimal, digits: int = 0) -> float:
    """SQL ROUND(x::numeric, digits): ties away from zero (Python's round() rounds ties to even)."""
    return float(Decimal(str(value)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


def fmt_duration(seconds: int) -> str:
    return f"{seconds // 3600}h {(seconds % 3600) // 60}m"


def history_points(
    days: Sequence[date], values: Mapping[date, float], label: Callable[[float], str]
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for day in days:
        value = float(values.get(day, 0.0))
        out.append({"date": day.isoformat(), "value": value, "label": label(value)})
    return out


def empty_card() -> dict[str, object]:
    return {"tile": None, "featured": None, "rings": {}}


Build = Callable[[UnitOfWork, DashboardContext], Awaitable[Mapping[str, object]]]


class DashboardSkill:
    def __init__(self, *, uow: UnitOfWorkFactory, clock: Clock, build: Build, name: str) -> None:
        self._uow = uow
        self._clock = clock
        self._build = build
        self._name = name

    async def __call__(self, request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        uid = request.user_id
        async with self._uow.for_user(uid) as tx:
            settings = await tx.repo(UserSettingsRepository).get(uid)
            data = await self._build(tx, DashboardContext(uid, settings, self._clock.now()))
        return SkillResult(output=self._name, data=dict(data))
