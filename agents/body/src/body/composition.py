"""Composition root: the only place that chooses adapters."""

from __future__ import annotations

from dataclasses import dataclass

from a2a.types import AgentCard
from shared.a2a.executor import SkillExecutor, SkillHandler
from shared.adapters.a2a.task_store import SqlTaskStore
from shared.adapters.agent_base import base_repositories, build_agent_base
from shared.adapters.chat_model.factory import LangChainChatModelFactory
from shared.adapters.db.profile import SqlBodyProfiles
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.analysis.skill import AnalysisSkill, AnalysisSpec
from shared.ports.clock import Clock
from shared.ports.llm import LLMProvider
from shared.ports.peers import PeerClient
from shared.ports.profile import BodyProfileRepository
from shared.ports.vector_memory import VectorMemory
from shared.skill_ids import Body
from sqlalchemy.ext.asyncio import AsyncEngine

from body.adapters.a2a.card import PEER_SKILLS, build_agent_card
from body.adapters.pdf import PdfplumberReader
from body.adapters.vision import ChatModelVision
from body.application.data import BodyData
from body.application.import_vihealth import ImportViHealth
from body.application.ports import ReportReader, ReportVision
from body.settings import BodySettings

AGENT = "body"
BODY_SPEC = AnalysisSpec(
    agent=AGENT,
    tails={
        Body.GET_LATEST: (
            "State the most recent weight, body fat %, and any standouts (score, "
            "visceral fat) in 1–3 sentences plain text. No markdown."
        ),
        Body.ANALYZE_TREND: (
            "Respond in 6–10 lines plain text: (1) weight / fat / muscle trend "
            "grounded in the body history, (2) one mechanism (recomposition vs "
            "deficit vs hypertrophy phase) tied to the data, (3) one observation "
            "linking peer nutrition / workout / recovery context if present. "
            "Redirect cross-domain prescriptions ('eat fewer carbs', 'lift "
            "heavier') to /nutrition or /workout. No markdown."
        ),
    },
    peer_order=("nutrition", "workout", "recovery"),
    peer_skills=PEER_SKILLS,
)


@dataclass(frozen=True, slots=True)
class BodyRuntime:
    executor: SkillExecutor
    task_store: SqlTaskStore
    card: AgentCard
    engine: AsyncEngine


def build_runtime(
    settings: BodySettings,
    *,
    llm: LLMProvider | None = None,
    peers: PeerClient | None = None,
    memory: VectorMemory | None = None,
    clock: Clock | None = None,
    reader: ReportReader | None = None,
    vision: ReportVision | None = None,
) -> BodyRuntime:
    base = build_agent_base(settings, llm=llm, peers=peers, memory=memory, clock=clock)
    uow = SqlUnitOfWorkFactory(
        base.engine, {**base_repositories(), BodyProfileRepository: SqlBodyProfiles}
    )

    def analysis(mode: str) -> AnalysisSkill:
        return AnalysisSkill(
            spec=BODY_SPEC,
            mode=mode,
            data=BodyData(),
            llm=base.llm,
            uow=uow,
            peers=base.peers,
            memory=base.memory,
            clock=base.clock,
            translator=base.translator,
            default_locale=base.default_locale,
        )

    handlers: dict[str, SkillHandler] = {
        Body.IMPORT_VIHEALTH: ImportViHealth(
            reader=reader or PdfplumberReader(),
            vision=vision or ChatModelVision(LangChainChatModelFactory(settings)),
            uow=uow,
            translator=base.translator,
            default_locale=base.default_locale,
        ),
        Body.GET_LATEST: analysis(Body.GET_LATEST),
        Body.ANALYZE_TREND: analysis(Body.ANALYZE_TREND),
    }
    return BodyRuntime(
        executor=SkillExecutor(
            agent=AGENT,
            handlers=handlers,
            routable=[Body.GET_LATEST, Body.ANALYZE_TREND],
            peers=list(PEER_SKILLS),
            llm=base.llm,
            task_records=base.task_records,
            clock=base.clock,
        ),
        task_store=SqlTaskStore(base.engine, agent=AGENT),
        card=build_agent_card(settings.body_agent_url),
        engine=base.engine,
    )
