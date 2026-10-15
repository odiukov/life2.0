"""Static agent directory (URLs from settings), cached agent cards, live health, and GET /agents."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import datetime
from time import monotonic
from typing import Any, Protocol
from uuid import UUID

import httpx
from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH
from fastapi import APIRouter, Depends
from household.adapters.http import Authenticate
from shared.ports.clock import Clock
from shared.ports.uow import UnitOfWorkFactory
from shared.ports.users import UserSettingsRepository
from shared.schema.tables import tasks
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection

CARD_PATH = AGENT_CARD_WELL_KNOWN_PATH.lstrip("/")


class AgentDirectory:
    def __init__(
        self,
        urls: Mapping[str, str],
        http: httpx.AsyncClient,
        *,
        card_ttl_s: float = 300.0,
        health_timeout_s: float = 3.0,
    ) -> None:
        self._urls = {name: url.rstrip("/") + "/" for name, url in urls.items()}
        self._http = http
        self._ttl = card_ttl_s
        self._timeout = health_timeout_s
        self._cards: dict[str, tuple[float, dict[str, Any]]] = {}

    def names(self) -> list[str]:
        return list(self._urls)

    def url(self, name: str) -> str:
        return self._urls[name]

    async def card(self, name: str) -> dict[str, Any] | None:
        cached = self._cards.get(name)
        if cached and monotonic() - cached[0] < self._ttl:
            return cached[1]
        try:
            response = await self._http.get(self._urls[name] + CARD_PATH, timeout=self._timeout)
            response.raise_for_status()
            card = dict(response.json())
        except (httpx.HTTPError, ValueError, TypeError):
            return cached[1] if cached else None
        self._cards[name] = (monotonic(), card)
        return card

    async def online(self, name: str) -> bool:
        try:
            response = await self._http.get(self._urls[name] + "health", timeout=self._timeout)
        except httpx.HTTPError:
            return False
        return response.status_code == 200


class TaskCounts(Protocol):
    async def since(self, user_id: UUID, agent: str, start: datetime) -> int: ...


class SqlTaskCounts:
    """tasks has no RLS and no user column: the caller's runs are those whose input names them."""

    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def since(self, user_id: UUID, agent: str, start: datetime) -> int:
        c = tasks.c
        query = select(func.count()).where(
            c.agent == agent, c.created_at >= start, c.input["user_id"].astext == str(user_id)
        )
        return int((await self._conn.execute(query)).scalar_one())


def build_agents_router(
    directory: AgentDirectory, uow: UnitOfWorkFactory, clock: Clock, authenticate: Authenticate
) -> APIRouter:
    router = APIRouter(tags=["agents"])

    user_dependency = Depends(authenticate)

    @router.get("/agents")
    async def agents(user: UUID = user_dependency) -> dict[str, list[dict[str, Any]]]:
        async with uow.for_user(user) as tx:
            settings = await tx.repo(UserSettingsRepository).get(user)
            start = datetime.combine(
                settings.today(clock.now()), datetime.min.time(), tzinfo=settings.timezone
            )
            counts = {
                name: await tx.repo(TaskCounts).since(user, name, start)
                for name in directory.names()
            }

        async def describe(name: str) -> dict[str, Any]:
            raw_card, online = await asyncio.gather(directory.card(name), directory.online(name))
            card = raw_card or {}
            return {
                "name": name,
                "url": directory.url(name),
                "online": online,
                "skills": [
                    {"id": s.get("id", ""), "name": s.get("name", s.get("id", ""))}
                    for s in card.get("skills") or []
                ],
                "description": card.get("description", ""),
                "tasks_today": counts[name],
            }

        return {
            "agents": list(await asyncio.gather(*(describe(name) for name in directory.names())))
        }

    return router
