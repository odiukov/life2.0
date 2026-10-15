"""Composition root: the only place that chooses adapters."""

from __future__ import annotations

from dataclasses import dataclass

from a2a.types import AgentCard
from shared.a2a.executor import SkillExecutor, SkillHandler
from shared.adapters.a2a.task_records import SqlTaskRecords
from shared.adapters.a2a.task_store import SqlTaskStore
from shared.adapters.agent_base import base_repositories
from shared.adapters.clock import SystemClock
from shared.adapters.db.engine import create_engine
from shared.adapters.db.profile import SqlBodyProfiles
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.adapters.i18n import JsonTranslator
from shared.adapters.llm.build import build_llm_provider
from shared.adapters.peers import A2APeerClient
from shared.adapters.vector import QdrantVectorMemory
from shared.dashboard import DashboardSkill
from shared.observability.logging import configure_logging
from shared.ports.clock import Clock
from shared.ports.llm import LLMProvider
from shared.ports.peers import PeerClient
from shared.ports.profile import BodyProfileRepository
from shared.ports.vector_memory import VectorMemory
from shared.skill_ids import Dashboard, Nutrition
from sqlalchemy.ext.asyncio import AsyncEngine

from nutrition.adapters.a2a.card import build_agent_card
from nutrition.adapters.db import nutrition_uow
from nutrition.adapters.sync import HttpNutritionSync
from nutrition.application.analyze import AnalyzeNutrition
from nutrition.application.dashboard import card, detail
from nutrition.application.log_meal import LogMeal
from nutrition.application.peers import PEER_SKILLS
from nutrition.application.ports import NutritionSync
from nutrition.application.prompts import AnalysisMode
from nutrition.application.set_body_profile import SetBodyProfile
from nutrition.settings import NutritionSettings

AGENT = "nutrition"


@dataclass(frozen=True, slots=True)
class NutritionRuntime:
    executor: SkillExecutor
    task_store: SqlTaskStore
    card: AgentCard
    engine: AsyncEngine


def build_runtime(
    settings: NutritionSettings,
    *,
    llm: LLMProvider | None = None,
    memory: VectorMemory | None = None,
    peers: PeerClient | None = None,
    sync: NutritionSync | None = None,
    clock: Clock | None = None,
) -> NutritionRuntime:
    configure_logging(settings.telemetry)
    engine = create_engine(settings.database)
    uow = nutrition_uow(engine)
    llm = llm if llm is not None else build_llm_provider(settings)
    memory = memory if memory is not None else QdrantVectorMemory()
    peers = peers if peers is not None else A2APeerClient()
    sync = sync if sync is not None else HttpNutritionSync(settings.sync_service_url)
    clock = clock if clock is not None else SystemClock()
    translator = JsonTranslator.from_dir(settings.i18n_locales_dir)
    locale = settings.default_locale

    def analysis(mode: AnalysisMode) -> AnalyzeNutrition:
        return AnalyzeNutrition(
            mode=mode,
            llm=llm,
            uow=uow,
            clock=clock,
            translator=translator,
            peers=peers,
            memory=memory,
            sync=sync,
            default_locale=locale,
        )

    handlers: dict[str, SkillHandler] = {
        Nutrition.LOG_MEAL: LogMeal(
            llm=llm,
            uow=uow,
            clock=clock,
            translator=translator,
            memory=memory,
            default_locale=locale,
        ),
        Nutrition.ANALYZE: analysis("analyze_nutrition"),
        Nutrition.RECOMMENDATIONS: analysis("get_recommendations"),
        Nutrition.SET_BODY_PROFILE: SetBodyProfile(
            llm=llm, uow=uow, translator=translator, default_locale=locale
        ),
    }
    dashboard_uow = SqlUnitOfWorkFactory(
        engine, {**base_repositories(), BodyProfileRepository: SqlBodyProfiles}
    )
    routable = tuple(handlers)
    handlers[Dashboard.CARD] = DashboardSkill(
        uow=dashboard_uow, clock=clock, build=card, name=Dashboard.CARD
    )
    handlers[Dashboard.DETAIL] = DashboardSkill(
        uow=dashboard_uow, clock=clock, build=detail, name=Dashboard.DETAIL
    )
    executor = SkillExecutor(
        agent=AGENT,
        handlers=handlers,
        routable=routable,
        peers=list(PEER_SKILLS),
        llm=llm,
        task_records=SqlTaskRecords(engine),
        clock=clock,
    )
    return NutritionRuntime(
        executor=executor,
        task_store=SqlTaskStore(engine, agent=AGENT),
        card=build_agent_card(settings.nutrition_agent_url),
        engine=engine,
    )
