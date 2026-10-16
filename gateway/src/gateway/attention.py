"""The "now" block on Me: attention items from participating agents, minus the user's dismissals."""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import Callable, Mapping, Sequence
from typing import Annotated, Literal, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from household.adapters.http import Authenticate
from pydantic import BaseModel, Field, ValidationError, field_validator
from shared.attention import DETAIL_LIMIT, LEVEL_ORDER, MAX_ITEMS, TEXT_LIMIT
from shared.observability.logging import get_logger
from shared.ports.clock import Clock
from shared.ports.skills import SkillCallError, SkillClient, SkillUnavailable
from shared.ports.uow import UnitOfWorkFactory
from shared.ports.users import UserSettingsRepository
from shared.schema.tables import attention_dismissals
from shared.skill_ids import Attention
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

logger = get_logger(__name__)
ATTENTION_AGENTS = (
    "kitchen",
    "recovery",
    "sleep",
    "workout",
    "nutrition",
    "mood",
    "habits",
    "medication",
    "body",
)
Line = Annotated[str, Field(min_length=1, strict=True)]


class AttentionDismissals(Protocol):
    async def active(self, user_id: UUID, today: dt.date) -> set[str]:
        """Ids hidden for `user_id` on `today` (their until_date is after today)."""
        ...

    async def dismiss(self, user_id: UUID, item_id: str, until: dt.date) -> None: ...


class SqlAttentionDismissals:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def active(self, user_id: UUID, today: dt.date) -> set[str]:
        c = attention_dismissals.c
        rows = await self._conn.execute(
            select(c.item_id).where(c.user_id == user_id, c.until_date > today)
        )
        return {r.item_id for r in rows}

    async def dismiss(self, user_id: UUID, item_id: str, until: dt.date) -> None:
        stmt = insert(attention_dismissals).values(
            user_id=user_id, item_id=item_id, until_date=until
        )
        await self._conn.execute(
            stmt.on_conflict_do_update(
                constraint="attention_dismissals_pkey",
                set_={"until_date": stmt.excluded.until_date},
            )
        )


class ActionOut(BaseModel):
    type: Literal["agent", "task", "profile"]
    prompt: Annotated[str, Field(min_length=1, max_length=DETAIL_LIMIT, strict=True)] | None = None


class AttentionItemOut(BaseModel):
    agent: str
    id: Line
    level: Literal["critical", "high", "normal"]
    rank: Annotated[int, Field(strict=True)]
    text: Annotated[str, Field(min_length=1, max_length=TEXT_LIMIT, strict=True)]
    detail: Annotated[str, Field(min_length=1, max_length=DETAIL_LIMIT, strict=True)] | None = None
    action: ActionOut

    @field_validator("text", "detail")
    @classmethod
    def single_line(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or "\n" in value):
            raise ValueError("invalid_text")
        return value


class AttentionOut(BaseModel):
    items: list[AttentionItemOut]
    unavailable: list[str]


async def _ask(
    client: SkillClient, agent: str, user: UUID, timeout_s: float
) -> list[AttentionItemOut] | None:
    try:
        async with asyncio.timeout(timeout_s):
            reply = await client.call(skill_id=Attention.ITEMS, user_id=user, params={})
    except (SkillUnavailable, SkillCallError, TimeoutError) as exc:
        logger.warning("attention_agent_unavailable", agent=agent, error_type=type(exc).__name__)
        return None
    data = reply.data
    raw = data.get("items") if isinstance(data, Mapping) else None
    if not isinstance(raw, list) or len(raw) > MAX_ITEMS:
        return None
    items: list[AttentionItemOut] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            return None
        try:
            item = AttentionItemOut.model_validate({**entry, "agent": agent})
        except ValidationError:
            return None
        if not item.id.startswith(f"{agent}:"):
            return None
        items.append(item)
    return items


def merge(
    results: Mapping[str, Sequence[AttentionItemOut] | None], hidden: set[str]
) -> AttentionOut:
    items: list[AttentionItemOut] = []
    unavailable: list[str] = []
    for agent in ATTENTION_AGENTS:
        batch = results.get(agent)
        if batch is None:
            unavailable.append(agent)
            continue
        items.extend(i for i in batch if i.level == "critical" or i.id not in hidden)
    order = {a: n for n, a in enumerate(ATTENTION_AGENTS)}
    items.sort(key=lambda i: (LEVEL_ORDER[i.level], i.rank, order[i.agent], i.id))
    return AttentionOut(items=items, unavailable=unavailable)


def build_router(
    clients: Callable[[str], SkillClient],
    uow: UnitOfWorkFactory,
    clock: Clock,
    authenticate: Authenticate,
    *,
    timeout_s: float = 3.0,
) -> APIRouter:
    router = APIRouter(tags=["attention"])
    user_dependency = Depends(authenticate)

    async def today_for(user: UUID) -> dt.date:
        async with uow.for_user(user) as tx:
            settings = await tx.repo(UserSettingsRepository).get(user)
        return settings.today(clock.now())

    @router.get("/me/attention", response_model=AttentionOut)
    async def attention(user: UUID = user_dependency) -> AttentionOut:
        today = await today_for(user)
        results = await asyncio.gather(
            *(_ask(clients(a), a, user, timeout_s) for a in ATTENTION_AGENTS)
        )
        async with uow.for_user(user) as tx:
            hidden = await tx.repo(AttentionDismissals).active(user, today)
        return merge(dict(zip(ATTENTION_AGENTS, results, strict=True)), hidden)

    @router.post("/me/attention/{item_id}/dismiss", status_code=204)
    async def dismiss(item_id: str, user: UUID = user_dependency) -> Response:
        agent = item_id.split(":", 1)[0]
        if agent not in ATTENTION_AGENTS:
            raise HTTPException(status_code=404, detail="unknown_item")
        current = await _ask(clients(agent), agent, user, timeout_s)
        if current is None:
            raise HTTPException(status_code=503, detail="agent_unavailable")
        found = next((i for i in current if i.id == item_id), None)
        if found is None:
            raise HTTPException(status_code=404, detail="unknown_item")
        if found.level == "critical":
            raise HTTPException(status_code=409, detail="not_dismissable")
        today = await today_for(user)
        async with uow.for_user(user) as tx:
            await tx.repo(AttentionDismissals).dismiss(user, item_id, today + dt.timedelta(days=1))
        return Response(status_code=204)

    return router
