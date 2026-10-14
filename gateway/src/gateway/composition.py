"""Composition root of the gateway: the only place that chooses adapters."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from uuid import UUID

import httpx
from fastapi import APIRouter, FastAPI
from household.adapters.db import household_uow
from household.adapters.http import Authenticate, build_router
from household.application.service import HouseholdService
from pydantic import ValidationError
from shared.adapters.clock import SystemClock
from shared.adapters.db.engine import create_engine
from shared.ports.clock import Clock
from shared.ports.skills import SkillClient
from shared.ports.stt import SpeechToText

from gateway.hooks import HouseholdEnsurer
from gateway.settings import GatewaySettings


class GatewayNotConfigured(Exception):
    """DATABASE__DSN (or another required setting) is missing; the orchestrator runs without it."""


@dataclass
class Gateway:
    routers: list[APIRouter]
    post_auth_hook: Callable[[UUID], Awaitable[None]]
    _closers: list[Callable[[], Awaitable[None]]] = field(default_factory=list)

    async def aclose(self) -> None:
        for close in reversed(self._closers):
            await close()


def build_gateway(
    settings: GatewaySettings,
    *,
    authenticate: Authenticate,
    clock: Clock | None = None,
    http: httpx.AsyncClient | None = None,
    skill_client: SkillClient | None = None,
    stt: SpeechToText | None = None,
) -> Gateway:
    clock = clock or SystemClock()
    engine = create_engine(settings.database)
    http = http or httpx.AsyncClient()
    households = HouseholdService(household_uow(engine), clock)
    routers = [build_router(households, authenticate)]
    return Gateway(
        routers=routers,
        post_auth_hook=HouseholdEnsurer(households),
        _closers=[engine.dispose, http.aclose],
    )


def build_gateway_from_env(*, authenticate: Authenticate) -> Gateway:
    try:
        settings = GatewaySettings()
    except ValidationError as exc:
        raise GatewayNotConfigured(str(exc.errors()[0]["loc"])) from exc
    return build_gateway(settings, authenticate=authenticate)


def mount(app: FastAPI, gateway: Gateway) -> None:
    for router in gateway.routers:
        app.include_router(router)
