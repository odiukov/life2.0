"""Composition root: the only place that chooses adapters."""

from __future__ import annotations

from dataclasses import dataclass

from a2a.types import AgentCard
from shared.a2a.executor import SkillExecutor, SkillHandler
from shared.adapters.a2a.task_store import SqlTaskStore
from shared.adapters.agent_base import base_repositories, build_agent_base
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.analysis.skill import AnalysisSkill, AnalysisSpec
from shared.attention import AttentionSkill
from shared.dashboard import DashboardSkill
from shared.feed import FeedSkill
from shared.ports.clock import Clock
from shared.ports.llm import LLMProvider
from shared.ports.peers import PeerClient
from shared.ports.vector_memory import VectorMemory
from shared.skill_ids import Attention, Dashboard, Feed
from shared.skill_ids import Medication as MedicationSkill
from sqlalchemy.ext.asyncio import AsyncEngine

from medication.adapters.a2a.card import PEER_SKILLS, build_agent_card
from medication.adapters.db import medication_repositories
from medication.application.archive import ArchiveMedication
from medication.application.attention import collect as attention_collect
from medication.application.dashboard import card, detail
from medication.application.data import AdherenceData
from medication.application.define import DefineMedication
from medication.application.feed import collect as feed_collect
from medication.application.intake import LogIntake
from medication.application.listing import ListActive
from medication.settings import MedicationSettings

AGENT = "medication"
MEDICATION_SPEC = AnalysisSpec(
    agent=AGENT,
    tails={
        MedicationSkill.ANALYZE: (
            "Respond in 4–6 lines plain text: adherence rate per medication, miss streaks, dose-timing "
            "pattern. Redirect mood / sleep / recovery effects to the relevant peer. No markdown."
        ),
    },
    peer_order=("mood", "sleep", "recovery"),
    peer_skills=PEER_SKILLS,
    memories=False,  # the legacy adherence prompt had no memories
)


@dataclass(frozen=True, slots=True)
class MedicationRuntime:
    executor: SkillExecutor
    task_store: SqlTaskStore
    card: AgentCard
    engine: AsyncEngine


def build_runtime(
    settings: MedicationSettings,
    *,
    llm: LLMProvider | None = None,
    peers: PeerClient | None = None,
    memory: VectorMemory | None = None,
    clock: Clock | None = None,
) -> MedicationRuntime:
    base = build_agent_base(settings, llm=llm, peers=peers, memory=memory, clock=clock)
    uow = SqlUnitOfWorkFactory(base.engine, {**base_repositories(), **medication_repositories()})
    handlers: dict[str, SkillHandler] = {
        MedicationSkill.DEFINE: DefineMedication(
            llm=base.llm,
            uow=uow,
            clock=base.clock,
            translator=base.translator,
            memory=base.memory,
            default_locale=base.default_locale,
        ),
        MedicationSkill.LOG: LogIntake(
            llm=base.llm,
            uow=uow,
            clock=base.clock,
            translator=base.translator,
            memory=base.memory,
            default_locale=base.default_locale,
        ),
        MedicationSkill.LIST: ListActive(
            uow=uow, translator=base.translator, default_locale=base.default_locale
        ),
        MedicationSkill.ARCHIVE: ArchiveMedication(
            llm=base.llm,
            uow=uow,
            clock=base.clock,
            translator=base.translator,
            memory=base.memory,
            default_locale=base.default_locale,
        ),
        MedicationSkill.ANALYZE: AnalysisSkill(
            spec=MEDICATION_SPEC,
            mode=MedicationSkill.ANALYZE,
            data=AdherenceData(base.translator, base.default_locale),
            llm=base.llm,
            uow=uow,
            peers=base.peers,
            memory=base.memory,
            clock=base.clock,
            translator=base.translator,
            default_locale=base.default_locale,
        ),
    }
    routable = tuple(handlers)
    handlers[Feed.EVENTS] = FeedSkill(
        uow=uow,
        clock=base.clock,
        translator=base.translator,
        default_locale=base.default_locale,
        collect=feed_collect,
    )
    handlers[Dashboard.CARD] = DashboardSkill(
        uow=uow, clock=base.clock, build=card, name=Dashboard.CARD
    )
    handlers[Dashboard.DETAIL] = DashboardSkill(
        uow=uow, clock=base.clock, build=detail, name=Dashboard.DETAIL
    )
    handlers[Attention.ITEMS] = AttentionSkill(
        uow=uow,
        clock=base.clock,
        translator=base.translator,
        default_locale=base.default_locale,
        collect=attention_collect,
    )
    return MedicationRuntime(
        executor=SkillExecutor(
            agent=AGENT,
            handlers=handlers,
            routable=routable,
            peers=list(PEER_SKILLS),
            llm=base.llm,
            task_records=base.task_records,
            clock=base.clock,
        ),
        task_store=SqlTaskStore(base.engine, agent=AGENT),
        card=build_agent_card(settings.medication_agent_url),
        engine=base.engine,
    )
