"""Composition root: the only place that chooses adapters."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from a2a.types import AgentCard
from shared.a2a.executor import SkillExecutor
from shared.adapters.a2a.task_records import SqlTaskRecords
from shared.adapters.a2a.task_store import SqlTaskStore
from shared.adapters.clock import SystemClock
from shared.adapters.db.credentials import sql_credential_store
from shared.adapters.db.engine import create_engine
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.adapters.db.users import SqlUserSettings
from shared.adapters.i18n import JsonTranslator
from shared.adapters.secrets import AesGcmSecretBox
from shared.observability.logging import configure_logging
from shared.ports.clock import Clock
from shared.ports.credentials import CredentialStore
from shared.ports.users import UserSettingsRepository
from shared.skill_ids import Dashboard
from sqlalchemy.ext.asyncio import AsyncEngine

from calendar_agent.adapters.a2a.card import build_agent_card
from calendar_agent.adapters.google import HttpGoogleCalendar, HttpGoogleOAuth
from calendar_agent.adapters.no_llm import NoLLM
from calendar_agent.application.dashboard import CalendarCard, CalendarDetail
from calendar_agent.application.ports import GoogleCalendar, GoogleOAuth
from calendar_agent.application.skills import build_skills
from calendar_agent.settings import CalendarSettings

AGENT = "calendar"


@dataclass(frozen=True, slots=True)
class CalendarRuntime:
    executor: SkillExecutor
    task_store: SqlTaskStore
    card: AgentCard
    engine: AsyncEngine
    http: httpx.AsyncClient


def build_runtime(
    settings: CalendarSettings,
    *,
    google: GoogleCalendar | None = None,
    oauth: GoogleOAuth | None = None,
    clock: Clock | None = None,
) -> CalendarRuntime:
    configure_logging(settings.telemetry)
    engine = create_engine(settings.database)
    box = AesGcmSecretBox.from_settings(settings.secrets)
    uow = SqlUnitOfWorkFactory(
        engine,
        {CredentialStore: sql_credential_store(box), UserSettingsRepository: SqlUserSettings},
    )
    clock = clock or SystemClock()
    http = httpx.AsyncClient()
    secret = settings.google_calendar_oauth_client_secret
    google = google or HttpGoogleCalendar(http)
    oauth = oauth or HttpGoogleOAuth(
        http,
        client_id=settings.google_calendar_oauth_client_id,
        client_secret=secret.get_secret_value() if secret else None,
        redirect_uri=settings.google_calendar_oauth_redirect_uri,
    )
    skills = build_skills(
        uow=uow,
        google=google,
        oauth=oauth,
        clock=clock,
        translator=JsonTranslator.from_dir(settings.i18n_locales_dir),
        default_locale=settings.default_locale,
    )
    skills[Dashboard.CARD] = CalendarCard(uow=uow, google=google, oauth=oauth, clock=clock)
    skills[Dashboard.DETAIL] = CalendarDetail(uow=uow, google=google, oauth=oauth, clock=clock)
    return CalendarRuntime(
        executor=SkillExecutor(
            agent=AGENT,
            handlers=skills,
            peers=[],
            llm=NoLLM(),
            task_records=SqlTaskRecords(engine),
            clock=clock,
            routable=[],
        ),
        task_store=SqlTaskStore(engine, agent=AGENT),
        card=build_agent_card(settings.calendar_agent_url),
        engine=engine,
        http=http,
    )
