"""What every health agent's composition root builds the same way."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from shared.adapters.a2a.task_records import SqlTaskRecords
from shared.adapters.clock import SystemClock
from shared.adapters.db.engine import create_engine
from shared.adapters.db.health_logs import SqlHealthLogs
from shared.adapters.db.users import SqlUserSettings
from shared.adapters.i18n import JsonTranslator
from shared.adapters.llm.build import build_llm_provider
from shared.adapters.peers import A2APeerClient
from shared.adapters.vector import QdrantVectorMemory
from shared.config import BaseServiceSettings
from shared.observability.logging import configure_logging
from shared.ports.clock import Clock
from shared.ports.health_logs import HealthLogRepository
from shared.ports.llm import LLMProvider
from shared.ports.peers import PeerClient
from shared.ports.translator import Translator
from shared.ports.users import UserSettingsRepository
from shared.ports.vector_memory import VectorMemory


@dataclass(frozen=True, slots=True)
class AgentBase:
    engine: AsyncEngine
    llm: LLMProvider
    peers: PeerClient
    memory: VectorMemory
    clock: Clock
    translator: Translator
    task_records: SqlTaskRecords
    default_locale: str


def base_repositories() -> dict[type[Any], Callable[[AsyncConnection], Any]]:
    return {UserSettingsRepository: SqlUserSettings, HealthLogRepository: SqlHealthLogs}


def build_agent_base(
    settings: BaseServiceSettings,
    *,
    llm: LLMProvider | None = None,
    peers: PeerClient | None = None,
    memory: VectorMemory | None = None,
    clock: Clock | None = None,
) -> AgentBase:
    configure_logging(settings.telemetry)
    engine = create_engine(settings.database)
    return AgentBase(
        engine=engine,
        llm=llm if llm is not None else build_llm_provider(settings),
        peers=peers if peers is not None else A2APeerClient(),
        memory=memory if memory is not None else QdrantVectorMemory(),
        clock=clock if clock is not None else SystemClock(),
        translator=JsonTranslator.from_dir(settings.i18n_locales_dir),
        task_records=SqlTaskRecords(engine),
        default_locale=settings.default_locale,
    )
