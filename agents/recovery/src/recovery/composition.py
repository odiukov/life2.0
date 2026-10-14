"""Composition root: the only place that chooses adapters."""

from __future__ import annotations

from dataclasses import dataclass

from a2a.types import AgentCard
from shared.a2a.executor import SkillExecutor, SkillHandler
from shared.adapters.a2a.task_store import SqlTaskStore
from shared.adapters.agent_base import base_repositories, build_agent_base
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.analysis.skill import AnalysisSkill, AnalysisSpec
from shared.ports.clock import Clock
from shared.ports.llm import LLMProvider
from shared.ports.peers import PeerClient
from shared.ports.vector_memory import VectorMemory
from shared.skill_ids import Recovery
from sqlalchemy.ext.asyncio import AsyncEngine

from recovery.adapters.a2a.card import PEER_SKILLS, build_agent_card
from recovery.application.data import RecoveryData
from recovery.settings import RecoverySettings

AGENT = "recovery"
RECOVERY_SPEC = AnalysisSpec(
    agent=AGENT,
    tails={
        Recovery.READINESS: (
            "State the bucket directly, then give one sentence per moved metric (HRV, RHR, stress, "
            "body battery) with its direction and magnitude grounded in the data. 3–5 lines plain text."
        ),
        Recovery.ANALYZE_TREND: (
            "6–10 lines plain text: (1) per-metric 7-day trend, (2) outlier days with a mechanism "
            "(e.g. allostatic load), (3) one correlation observation grounded in peer context if "
            "present. No markdown."
        ),
        Recovery.RECOMMENDATIONS: (
            "4–6 lines plain text with 2–3 concrete recovery-domain actions + the 'why' grounded in "
            "the bucket and recent metrics. Redirect training prescriptions to /workout. No markdown."
        ),
    },
    peer_order=("sleep", "workout", "nutrition", "mood"),
    peer_skills=PEER_SKILLS,
    memories=False,  # the legacy recovery prompt never included memories
)


@dataclass(frozen=True, slots=True)
class RecoveryRuntime:
    executor: SkillExecutor
    task_store: SqlTaskStore
    card: AgentCard
    engine: AsyncEngine


def build_runtime(
    settings: RecoverySettings,
    *,
    llm: LLMProvider | None = None,
    peers: PeerClient | None = None,
    memory: VectorMemory | None = None,
    clock: Clock | None = None,
) -> RecoveryRuntime:
    base = build_agent_base(settings, llm=llm, peers=peers, memory=memory, clock=clock)
    uow = SqlUnitOfWorkFactory(base.engine, base_repositories())
    handlers: dict[str, SkillHandler] = {
        skill: AnalysisSkill(
            spec=RECOVERY_SPEC,
            mode=skill,
            data=RecoveryData(skill),
            llm=base.llm,
            uow=uow,
            peers=base.peers,
            memory=base.memory,
            clock=base.clock,
            translator=base.translator,
            default_locale=base.default_locale,
        )
        for skill in (Recovery.READINESS, Recovery.ANALYZE_TREND, Recovery.RECOMMENDATIONS)
    }
    return RecoveryRuntime(
        executor=SkillExecutor(
            agent=AGENT,
            handlers=handlers,
            peers=list(PEER_SKILLS),
            llm=base.llm,
            task_records=base.task_records,
            clock=base.clock,
        ),
        task_store=SqlTaskStore(base.engine, agent=AGENT),
        card=build_agent_card(settings.recovery_agent_url),
        engine=base.engine,
    )
