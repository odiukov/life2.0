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
from shared.adapters.clock import SystemClock
from shared.adapters.db.credentials import sql_credential_store
from shared.adapters.db.engine import create_engine
from shared.adapters.db.health_logs import SqlHealthLogs
from shared.adapters.db.profile import SqlBodyProfiles
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.adapters.db.users import SqlUserSettings
from shared.adapters.notifications import notification_repositories
from shared.adapters.secrets import AesGcmSecretBox
from shared.adapters.stt import HttpSpeechToText
from shared.ports.clock import Clock
from shared.ports.credentials import CredentialStore
from shared.ports.health_logs import HealthLogRepository
from shared.ports.profile import BodyProfileRepository
from shared.ports.skills import SkillClient
from shared.ports.stt import SpeechToText
from shared.ports.uow import UnitOfWorkFactory
from shared.ports.users import UserSettingsRepository

from gateway.agents import AgentDirectory, SqlTaskCounts, TaskCounts, build_agents_router
from gateway.agents_client import AgentClients
from gateway.auth.authenticate import Authenticator
from gateway.auth.routes import build_router as build_auth_router
from gateway.auth.settings import AuthSettings
from gateway.auth.store import AuthStore, SqlAuthStore
from gateway.dashboard import build_router as build_dashboard_router
from gateway.hooks import HouseholdEnsurer
from gateway.integrations import (
    OAuthStateRepository,
    SourceActivity,
    SqlOAuthStates,
    SqlSourceActivity,
)
from gateway.integrations import build_router as build_integrations_router
from gateway.kitchen import KitchenGateway
from gateway.kitchen import build_router as build_kitchen_router
from gateway.notifications import build_router as build_notifications_router
from gateway.profile import build_router as build_profile_router
from gateway.settings import GatewaySettings
from gateway.sync import SyncTrigger, build_health_router, build_trigger_router
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
    clients = AgentClients(
        settings.agent_urls,
        http,
        timeout_s=settings.skill_timeout_s,
        timeouts={
            "body": settings.body_skill_timeout_s,
            "calendar": settings.calendar_skill_timeout_s,
        },
    )
    skill_client = skill_client or clients.client("kitchen")
    data_uow = SqlUnitOfWorkFactory(
        engine,
        {
            BodyProfileRepository: SqlBodyProfiles,
            HealthLogRepository: SqlHealthLogs,
            UserSettingsRepository: SqlUserSettings,
            CredentialStore: sql_credential_store(AesGcmSecretBox.from_settings(settings.secrets)),
            OAuthStateRepository: SqlOAuthStates,
            SourceActivity: SqlSourceActivity,
            TaskCounts: SqlTaskCounts,
        },
    )
    state_secret = (
        settings.oauth_state_secret.get_secret_value()
        if settings.oauth_state_secret
        else auth.secret()
    )
    trigger = SyncTrigger(http, settings.sync_url, concurrency=settings.sync_trigger_concurrency)
    stt = stt or HttpSpeechToText(settings.stt_url, http, timeout_s=settings.stt_timeout_s)
    auth_uow = uow or SqlUnitOfWorkFactory(engine, {AuthStore: SqlAuthStore})
    authenticate = Authenticator(auth, auth_uow)
    authenticate.add_hook(HouseholdEnsurer(households))
    directory = AgentDirectory(settings.agent_urls, http)
    routers = [
        build_dashboard_router(clients.client, directory, data_uow, authenticate),
        build_agents_router(directory, data_uow, clock, authenticate),
        build_auth_router(auth, auth_uow, http),
        build_router(households, authenticate),
        build_kitchen_router(KitchenGateway(skill_client), authenticate),
        build_notifications_router(
            SqlUnitOfWorkFactory(engine, notification_repositories()), clock, authenticate
        ),
        build_voice_router(stt, authenticate, max_bytes=settings.voice_max_bytes),
        build_profile_router(
            data_uow, clients.client("body"), authenticate, max_bytes=settings.upload_max_bytes
        ),
        build_integrations_router(
            settings,
            data_uow,
            clients.client,
            http,
            authenticate,
            clock=clock,
            state_key=state_secret.encode() if state_secret else None,
        ),
        build_trigger_router(trigger, authenticate),
        build_health_router(http, settings.sync_url, authenticate),
    ]
    return Gateway(
        routers=routers,
        authenticate=authenticate,
        _closers=[engine.dispose, http.aclose, trigger.aclose],
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
