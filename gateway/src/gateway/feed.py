"""The user's local-day feed assembled from personal agents' feed.events skills."""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import Callable, Mapping, Sequence
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from household.adapters.http import Authenticate
from pydantic import AwareDatetime, BaseModel, Field, ValidationError, field_validator
from shared.feed import MAX_ITEMS, TEXT_LIMIT, InvalidFeedDate, requested_day
from shared.observability.logging import get_logger
from shared.ports.clock import Clock
from shared.ports.skills import SkillCallError, SkillClient, SkillUnavailable
from shared.ports.uow import UnitOfWorkFactory
from shared.ports.users import UserSettingsRepository
from shared.skill_ids import Feed

logger = get_logger(__name__)
FEED_AGENTS = (
    "sleep",
    "workout",
    "nutrition",
    "body",
    "mood",
    "habits",
    "recovery",
    "medication",
    "calendar",
)


class FeedItemOut(BaseModel):
    agent: str
    id: Annotated[str, Field(min_length=1, strict=True)]
    at: AwareDatetime
    kind: Literal["event", "insight"]
    text: Annotated[str, Field(min_length=1, max_length=TEXT_LIMIT, strict=True)]

    @field_validator("text")
    @classmethod
    def nonblank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("empty_text")
        return value

    @field_validator("at", mode="before")
    @classmethod
    def timestamp_shape(cls, value: object) -> object:
        if not isinstance(value, (str, dt.datetime)):
            raise ValueError("invalid_timestamp")
        return value


class FeedOut(BaseModel):
    date: dt.date
    items: list[FeedItemOut]
    unavailable: list[str]


async def _ask(
    client: SkillClient, user: UUID, day: dt.date, zone: ZoneInfo, timeout_s: float
) -> list[FeedItemOut] | None:
    try:
        async with asyncio.timeout(timeout_s):
            reply = await client.call(
                skill_id=Feed.EVENTS, user_id=user, params={"date": day.isoformat()}
            )
    except (SkillUnavailable, SkillCallError, TimeoutError) as exc:
        logger.warning("feed_agent_unavailable", error_type=type(exc).__name__)
        return None
    data = reply.data
    if not isinstance(data, Mapping):
        return None
    raw_items = data.get("items")
    if not isinstance(raw_items, list) or len(raw_items) > MAX_ITEMS:
        return None
    items: list[FeedItemOut] = []
    for raw in raw_items:
        if not isinstance(raw, Mapping):
            return None
        try:
            item = FeedItemOut.model_validate({**raw, "agent": ""})
            local_day = item.at.astimezone(zone).date()
        except (ValidationError, OverflowError):
            return None
        if local_day != day:
            return None
        items.append(item)
    return items


def merge(day: dt.date, results: Mapping[str, Sequence[FeedItemOut] | None]) -> FeedOut:
    items: list[FeedItemOut] = []
    unavailable: list[str] = []
    for agent in FEED_AGENTS:
        batch = results.get(agent)
        if batch is None:
            unavailable.append(agent)
        else:
            items.extend(item.model_copy(update={"agent": agent}) for item in batch)
    items.sort(key=lambda item: item.at, reverse=True)
    return FeedOut(date=day, items=items, unavailable=unavailable)


def build_router(
    clients: Callable[[str], SkillClient],
    uow: UnitOfWorkFactory,
    clock: Clock,
    authenticate: Authenticate,
    *,
    timeout_s: float = 3.0,
) -> APIRouter:
    router = APIRouter(tags=["feed"])
    user_dependency = Depends(authenticate)

    @router.get("/me/feed", response_model=FeedOut)
    async def feed(
        day: str | None = Query(default=None, alias="date"), user: UUID = user_dependency
    ) -> FeedOut:
        async with uow.for_user(user) as tx:
            settings = await tx.repo(UserSettingsRepository).get(user)
        try:
            target = requested_day({"date": day}, settings.today(clock.now()))
        except InvalidFeedDate as exc:
            raise HTTPException(status_code=422, detail=exc.code) from None
        results = await asyncio.gather(
            *(_ask(clients(a), user, target, settings.timezone, timeout_s) for a in FEED_AGENTS)
        )
        return merge(target, dict(zip(FEED_AGENTS, results, strict=True)))

    return router
