"""Helpers for the structured `feed.events` skill every personal agent serves (no LLM).

An item is either something the agent already stores for the user's local day (an event) or the
insight its dashboard detail already computes (today only). Day windows come from the clock and
the user's zone, never from the database clock.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from shared.a2a.executor import SkillResult
from shared.a2a.request import SkillRequest
from shared.dashboard import DashboardContext
from shared.ports.clock import Clock
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWork, UnitOfWorkFactory
from shared.ports.users import UserSettingsRepository
from shared.skill_ids import Feed

MAX_ITEMS = 50
MAX_DAYS_BACK = 30
TEXT_LIMIT = 140
Kind = Literal["event", "insight"]


def clip(text: str) -> str:
    line = " ".join(text.split())
    return line if len(line) <= TEXT_LIMIT else line[: TEXT_LIMIT - 1] + "…"


@dataclass(frozen=True, slots=True)
class FeedItem:
    id: str
    at: datetime
    kind: Kind
    text: str

    def to_data(self) -> dict[str, object]:
        return {
            "id": self.id,
            "at": self.at.isoformat(),
            "kind": self.kind,
            "text": clip(self.text),
        }


@dataclass(frozen=True, slots=True)
class FeedContext:
    dashboard: DashboardContext
    day: date
    locale: str
    tr: Translator

    @property
    def user_id(self) -> UUID:
        return self.dashboard.user_id

    @property
    def zone(self) -> ZoneInfo:
        return self.dashboard.zone

    @property
    def is_today(self) -> bool:
        return self.day == self.dashboard.today

    def bounds(self) -> tuple[datetime, datetime]:
        return self.dashboard.bounds(self.day)

    def t(self, key: str, **params: object) -> str:
        return self.tr.t(key, self.locale, **params)

    def local(self, ts: datetime) -> datetime:
        return ts.astimezone(self.zone)


class InvalidFeedDate(ValueError):
    def __init__(self, code: Literal["invalid_params", "date_out_of_range"]) -> None:
        super().__init__(code)
        self.code = code


def requested_day(params: Mapping[str, object], today: date) -> date:
    raw = params.get("date")
    if raw is None:
        return today
    if not isinstance(raw, str):
        raise InvalidFeedDate("invalid_params")
    try:
        day = date.fromisoformat(raw)
    except ValueError:
        raise InvalidFeedDate("invalid_params") from None
    if day.isoformat() != raw:
        raise InvalidFeedDate("invalid_params")
    if day > today or day < today - timedelta(days=MAX_DAYS_BACK):
        raise InvalidFeedDate("date_out_of_range")
    return day


def row_id(agent: str, row: HealthLogRow) -> str:
    """(user, source, type, recorded_at) is unique in health_logs, so this id is stable."""
    return f"{agent}:{row.type}:{row.source}:{row.recorded_at.isoformat()}"


def duration_text(ctx: FeedContext, seconds: int) -> str:
    hours, minutes = seconds // 3600, (seconds % 3600) // 60
    return (
        ctx.t("feed.duration.hm", h=hours, m=minutes)
        if hours
        else ctx.t("feed.duration.m", m=minutes)
    )


async def day_rows(
    tx: UnitOfWork, ctx: FeedContext, *, types: Sequence[str], agent: str | None = None
) -> list[HealthLogRow]:
    start, end = ctx.bounds()
    rows = await tx.repo(HealthLogRepository).recent(
        ctx.user_id, types=list(types), since=start, agent=agent
    )
    return [r for r in rows if r.recorded_at < end]


def prefer_sources(
    rows: Iterable[HealthLogRow],
    priority: Sequence[str],
    *,
    same: Callable[[HealthLogRow, HealthLogRow], bool],
) -> list[HealthLogRow]:
    """Drop a row when a better-ranked source already holds the same thing (same(kept, row)).

    Sources not in `priority` rank last; the result is in `recorded_at` order.
    """
    rank = {source: i for i, source in enumerate(priority)}
    kept: list[HealthLogRow] = []
    for row in sorted(rows, key=lambda r: (rank.get(r.source, len(rank)), r.recorded_at)):
        if not any(k.source != row.source and same(k, row) for k in kept):
            kept.append(row)
    return sorted(kept, key=lambda r: r.recorded_at)


def insight_items(
    agent: str, ctx: FeedContext, detail: Mapping[str, object] | None
) -> list[FeedItem]:
    """Today's insight from the agent's own dashboard.detail data; nothing for past days."""
    insight = (detail or {}).get("insight")
    if not ctx.is_today or not isinstance(insight, str) or not insight.strip():
        return []
    return [
        FeedItem(f"{agent}:insight:{ctx.day.isoformat()}", ctx.dashboard.now, "insight", insight)
    ]


def feed_result(items: Iterable[FeedItem]) -> SkillResult:
    ordered = sorted(items, key=lambda i: i.at, reverse=True)[:MAX_ITEMS]
    return SkillResult(output=Feed.EVENTS, data={"items": [i.to_data() for i in ordered]})


Collect = Callable[[UnitOfWork, FeedContext], Awaitable[Iterable[FeedItem]]]


class FeedSkill:
    def __init__(
        self,
        *,
        uow: UnitOfWorkFactory,
        clock: Clock,
        translator: Translator,
        default_locale: str,
        collect: Collect,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._tr = translator
        self._default_locale = default_locale
        self._collect = collect

    async def __call__(self, request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        uid = request.user_id
        async with self._uow.for_user(uid) as tx:
            settings = await tx.repo(UserSettingsRepository).get(uid)
            dashboard = DashboardContext(uid, settings, self._clock.now())
            try:
                day = requested_day(request.params, dashboard.today)
            except InvalidFeedDate as exc:
                return SkillResult(output=exc.code, failed=True)
            ctx = FeedContext(dashboard, day, settings.locale or self._default_locale, self._tr)
            items = list(await self._collect(tx, ctx))
        return feed_result(items)
