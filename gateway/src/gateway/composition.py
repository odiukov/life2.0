"""Composition root of the gateway: the only place that chooses adapters."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx
from fastapi import APIRouter, FastAPI
from household.adapters.db import household_uow
from household.adapters.http import build_router
from household.application.service import HouseholdService
from pydantic import ValidationError
from shared.adapters.a2a.skill_client import A2ASkillClient
from shared.adapters.clock import SystemClock
from shared.adapters.db.engine import create_engine
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.adapters.notifications import notification_repositories
from shared.adapters.stt import HttpSpeechToText
from shared.ports.clock import Clock
from shared.ports.skills import SkillClient
from shared.ports.stt import SpeechToText
from shared.ports.uow import UnitOfWorkFactory

from gateway.auth.authenticate import Authenticator
from gateway.auth.routes import build_router as build_auth_router
from gateway.auth.settings import AuthSettings
from gateway.auth.store import AuthStore, SqlAuthStore
from gateway.hooks import HouseholdEnsurer
from gateway.kitchen import KitchenGateway
from gateway.kitchen import build_router as build_kitchen_router
from gateway.notifications import build_router as build_notifications_router
from gateway.settings import GatewaySettings
from gateway.voice import build_router as build_voice_router


class GatewayNotConfigured(Exception):
    """DATABASE__DSN (or another required setting) is missing; the orchestrator runs without it."""


@dataclass
class Gateway:
    routers: list[APIRouter]
    authenticate: Authenticator
    _closers: list[Callable[[], Awaitable[None]]] = field(default_factory=list)

    async def aclose(self) -> None:
        for close in reversed(self._closers):
            await close()


def build_gateway(
    settings: GatewaySettings,
    *,
    auth: AuthSettings | None = None,
    uow: UnitOfWorkFactory | None = None,
    clock: Clock | None = None,
    http: httpx.AsyncClient | None = None,
    skill_client: SkillClient | None = None,
    stt: SpeechToText | None = None,
) -> Gateway:
    try:
        auth = auth or AuthSettings()
    except ValidationError:
        raise RuntimeError("auth_configuration_invalid") from None
    clock = clock or SystemClock()
    engine = create_engine(settings.database)
    http = http or httpx.AsyncClient()
    households = HouseholdService(household_uow(engine), clock)
    skill_client = skill_client or A2ASkillClient(
        settings.kitchen_agent_url, http, timeout_s=settings.skill_timeout_s
    )
    stt = stt or HttpSpeechToText(settings.stt_url, http, timeout_s=settings.stt_timeout_s)
    auth_uow = uow or SqlUnitOfWorkFactory(engine, {AuthStore: SqlAuthStore})
    authenticate = Authenticator(auth, auth_uow)
    authenticate.add_hook(HouseholdEnsurer(households))
    routers = [
        build_auth_router(auth, auth_uow, http),
        build_router(households, authenticate),
        build_kitchen_router(KitchenGateway(skill_client), authenticate),
        build_notifications_router(
            SqlUnitOfWorkFactory(engine, notification_repositories()), clock, authenticate
        ),
        build_voice_router(stt, authenticate, max_bytes=settings.voice_max_bytes),
    ]
    return Gateway(
        routers=routers,
        authenticate=authenticate,
        _closers=[engine.dispose, http.aclose],
    )


def build_gateway_from_env() -> Gateway:
    try:
        settings = GatewaySettings()
    except ValidationError as exc:
        raise GatewayNotConfigured(str(exc.errors()[0]["loc"])) from None
    return build_gateway(settings)


def mount(app: FastAPI, gateway: Gateway) -> None:
    for router in gateway.routers:
        app.include_router(router)
