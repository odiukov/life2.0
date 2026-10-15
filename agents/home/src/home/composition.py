"""Composition root: the only place that chooses adapters."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from a2a.types import AgentCard
from shared.a2a.executor import SkillExecutor
from shared.adapters.a2a.task_records import SqlTaskRecords
from shared.adapters.a2a.task_store import SqlTaskStore
from shared.adapters.chat_model.factory import LangChainChatModelFactory
from shared.adapters.clock import SystemClock
from shared.adapters.db.engine import create_engine
from shared.adapters.db.household_credentials import sql_household_credentials
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.adapters.db.users import SqlUserSettings
from shared.adapters.i18n import JsonTranslator
from shared.adapters.llm.build import build_llm_provider
from shared.adapters.secrets import AesGcmSecretBox
from shared.observability.logging import configure_logging
from shared.ports.clock import Clock
from shared.ports.household_credentials import HouseholdCredentialStore
from shared.ports.users import UserSettingsRepository
from shared.skill_ids import Home
from sqlalchemy.ext.asyncio import AsyncEngine

from home.adapters.a2a.card import build_agent_card
from home.adapters.agent import LangGraphHomeAgent
from home.adapters.assistant import HttpHomeAssistant
from home.adapters.mcp_pool import McpPool
from home.application.ports import HomeAgent, HomeAssistant
from home.application.skills import build_skills
from home.settings import HomeSettings


@dataclass(frozen=True, slots=True)
class HomeRuntime:
    executor: SkillExecutor
    task_store: SqlTaskStore
    card: AgentCard
    engine: AsyncEngine
    http: httpx.AsyncClient
    pool: McpPool


def build_runtime(
    settings: HomeSettings,
    *,
    assistant: HomeAssistant | None = None,
    agent: HomeAgent | None = None,
    clock: Clock | None = None,
) -> HomeRuntime:
    configure_logging(settings.telemetry)
    engine = create_engine(settings.database)
    box = AesGcmSecretBox.from_settings(settings.secrets)
    uow = SqlUnitOfWorkFactory(
        engine,
        {
            HouseholdCredentialStore: sql_household_credentials(box),
            UserSettingsRepository: SqlUserSettings,
        },
    )
    clock = clock or SystemClock()
    http = httpx.AsyncClient()
    pool = McpPool(
        ttl_s=settings.mcp_session_ttl_s, connect_timeout_s=settings.mcp_connect_timeout_s
    )
    llm = build_llm_provider(settings)  # only for the executor's free-text routing between skills
    skills = build_skills(
        uow=uow,
        assistant=assistant or HttpHomeAssistant(http, pool),
        agent=agent or LangGraphHomeAgent(LangChainChatModelFactory(settings), pool),
        clock=clock,
        translator=JsonTranslator.from_dir(settings.i18n_locales_dir),
        default_locale=settings.default_locale,
        ask_timeout_s=settings.ask_timeout_s,
    )
    executor = SkillExecutor(
        agent="home",
        handlers=skills,
        peers=[],
        llm=llm,
        task_records=SqlTaskRecords(engine),
        clock=clock,
        routable=[Home.ASK],
    )
    return HomeRuntime(
        executor,
        SqlTaskStore(engine, agent="home"),
        build_agent_card(settings.home_agent_url),
        engine,
        http,
        pool,
    )
