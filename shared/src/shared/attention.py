"""Helpers for the structured `attention.items` skill: things that need doing, not yet scheduled.

Items come from rows the agent already stores, evaluated for the user's local today. No LLM.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from shared.a2a.executor import SkillResult
from shared.a2a.request import SkillRequest
from shared.dashboard import DashboardContext
from shared.ports.clock import Clock
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWork, UnitOfWorkFactory
from shared.ports.users import UserSettingsRepository
from shared.skill_ids import Attention

MAX_ITEMS = 10
TEXT_LIMIT = 80
DETAIL_LIMIT = 140
Level = Literal["critical", "high", "normal"]
ActionType = Literal["agent", "task", "profile"]
LEVEL_ORDER: dict[str, int] = {"critical": 0, "high": 1, "normal": 2}


def _clip(text: str, limit: int) -> str:
    line = " ".join(text.split())
    return line if len(line) <= limit else line[: limit - 1] + "…"


@dataclass(frozen=True, slots=True)
class AttentionAction:
    type: ActionType
    prompt: str | None = None

    def to_data(self) -> dict[str, object]:
        out: dict[str, object] = {"type": self.type}
        if self.prompt:
            out["prompt"] = _clip(self.prompt, DETAIL_LIMIT)
        return out


@dataclass(frozen=True, slots=True)
class AttentionItem:
    id: str
    level: Level
    rank: int
    text: str
    action: AttentionAction
    detail: str | None = None

    def to_data(self) -> dict[str, object]:
        out: dict[str, object] = {
            "id": self.id,
            "level": self.level,
            "rank": self.rank,
            "text": _clip(self.text, TEXT_LIMIT),
            "action": self.action.to_data(),
        }
        if self.detail and self.detail.strip():
            out["detail"] = _clip(self.detail, DETAIL_LIMIT)
        return out


@dataclass(frozen=True, slots=True)
class AttentionContext:
    dashboard: DashboardContext
    locale: str
    tr: Translator

    @property
    def user_id(self) -> UUID:
        return self.dashboard.user_id

    @property
    def zone(self) -> ZoneInfo:
        return self.dashboard.zone

    @property
    def today(self) -> date:
        return self.dashboard.today

    @property
    def now_local(self) -> datetime:
        return self.dashboard.now.astimezone(self.zone)

    def bounds(self, day: date) -> tuple[datetime, datetime]:
        return self.dashboard.bounds(day)

    def t(self, key: str, **params: object) -> str:
        return self.tr.t(key, self.locale, **params)


def days_since(ctx: AttentionContext, ts: datetime) -> int:
    """Whole local calendar days between `ts` and today (0 when `ts` is today)."""
    return (ctx.today - ts.astimezone(ctx.zone).date()).days


def attention_result(items: Iterable[AttentionItem]) -> SkillResult:
    ordered = sorted(items, key=lambda i: (LEVEL_ORDER[i.level], i.rank, i.id))[:MAX_ITEMS]
    return SkillResult(output=Attention.ITEMS, data={"items": [i.to_data() for i in ordered]})


Collect = Callable[[UnitOfWork, AttentionContext], Awaitable[Iterable[AttentionItem]]]


class AttentionSkill:
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
            ctx = AttentionContext(dashboard, settings.locale or self._default_locale, self._tr)
            items = list(await self._collect(tx, ctx))
        return attention_result(items)
