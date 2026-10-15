"""/dashboard/summary and /agents/{id}/detail: assembled from each agent's own dashboard skills."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from household.adapters.http import Authenticate
from shared.observability.logging import get_logger
from shared.ports.skills import SkillCallError, SkillClient, SkillUnavailable
from shared.ports.uow import UnitOfWorkFactory
from shared.skill_ids import Dashboard

from gateway.agents import AgentDirectory

logger = get_logger(__name__)
CARD_AGENTS = (
    "sleep",
    "recovery",
    "workout",
    "nutrition",
    "mood",
    "habits",
    "medication",
    "calendar",
    "body",
)
DETAIL_AGENTS = frozenset(
    {
        "sleep",
        "workout",
        "nutrition",
        "mood",
        "habits",
        "recovery",
        "medication",
        "finance",
        "calendar",
    }
)
RINGS = ("readyPct", "hrvPct", "hrvMs", "moodPct", "stepsPct")
FEATURED = {
    "sleep": "featured_sleep",
    "workout": "featured_workout",
    "nutrition": "featured_nutrition",
    "body": "featured_body",
}


async def _ask(
    client: SkillClient, skill: str, user: UUID, timeout_s: float
) -> Mapping[str, Any] | None:
    try:
        async with asyncio.timeout(timeout_s):
            reply = await client.call(skill_id=skill, user_id=user, params={})
    except (SkillUnavailable, SkillCallError, TimeoutError) as exc:
        logger.warning("dashboard_agent_unavailable", skill=skill, error_type=type(exc).__name__)
        return None
    return reply.data


def assemble(cards: Mapping[str, Mapping[str, Any] | None]) -> dict[str, Any]:
    tiles = [
        card["tile"] for agent in CARD_AGENTS if (card := cards.get(agent)) and card.get("tile")
    ]
    rings: dict[str, Any] = dict.fromkeys(RINGS)
    for card in cards.values():
        if card:
            rings.update({k: v for k, v in (card.get("rings") or {}).items() if k in rings})
    out: dict[str, Any] = {"agents": tiles, "rings": rings}
    for agent, key in FEATURED.items():
        card = cards.get(agent)
        out[key] = card.get("featured") if card else None
    out["unavailable"] = [agent for agent in CARD_AGENTS if cards.get(agent) is None]
    return out


def build_router(
    clients: Callable[[str], SkillClient],
    directory: AgentDirectory,
    counts: UnitOfWorkFactory,
    authenticate: Authenticate,
    *,
    timeout_s: float = 3.0,
) -> APIRouter:
    router = APIRouter(tags=["dashboard"])
    user_dependency = Depends(authenticate)

    @router.get("/dashboard/summary")
    async def summary(user: UUID = user_dependency) -> dict[str, Any]:
        results = await asyncio.gather(
            *(_ask(clients(a), Dashboard.CARD, user, timeout_s) for a in CARD_AGENTS)
        )
        return assemble(dict(zip(CARD_AGENTS, results, strict=True)))

    @router.get("/agents/{agent_id}/detail")
    async def detail(agent_id: str, user: UUID = user_dependency) -> Mapping[str, Any]:
        if agent_id not in DETAIL_AGENTS:
            raise HTTPException(status_code=404, detail="unknown_agent")
        data = await _ask(clients(agent_id), Dashboard.DETAIL, user, timeout_s * 3)
        if data is None:
            raise HTTPException(status_code=503, detail="agent_unavailable")
        return data

    return router
