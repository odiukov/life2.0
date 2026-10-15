"""Composition root: the only place that chooses adapters."""

from __future__ import annotations

from dataclasses import dataclass

from a2a.types import AgentCard
from shared.a2a.executor import SkillExecutor, SkillHandler
from shared.adapters.a2a.task_store import SqlTaskStore
from shared.adapters.agent_base import base_repositories, build_agent_base
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.analysis.skill import AnalysisSkill, AnalysisSpec
from shared.dashboard import DashboardSkill
from shared.ports.clock import Clock
from shared.ports.llm import LLMProvider
from shared.ports.peers import PeerClient
from shared.ports.vector_memory import VectorMemory
from shared.skill_ids import Dashboard
from shared.skill_ids import Workout as WorkoutSkill
from sqlalchemy.ext.asyncio import AsyncEngine

from workout.adapters.a2a.card import PEER_SKILLS, build_agent_card
from workout.application.dashboard import card, detail
from workout.application.data import WorkoutData
from workout.application.log_workout import LogWorkout
from workout.settings import WorkoutSettings

AGENT = "workout"
WORKOUT_SPEC = AnalysisSpec(
    agent=AGENT,
    tails={
        WorkoutSkill.ANALYZE: (
            "Respond in 6–10 lines plain text: (1) volume + intensity over the "
            "last 7–14 days grounded in the logs, (2) one mechanism (e.g. "
            "eccentric vs concentric load) tied to the user's pattern, (3) one "
            "implication for readiness. No markdown."
        ),
        WorkoutSkill.RECOMMENDATIONS: (
            "Respond in 4–6 lines plain text: 2–3 concrete training-domain "
            "actions for the next session + the 'why' grounded in the data. "
            "Redirect nutrition asks to /nutrition, sleep to /sleep, recovery "
            "to /recovery. No markdown."
        ),
    },
    peer_order=("recovery", "sleep", "nutrition", "body", "habits", "medication"),
    peer_skills=PEER_SKILLS,
)


@dataclass(frozen=True, slots=True)
class WorkoutRuntime:
    executor: SkillExecutor
    task_store: SqlTaskStore
    card: AgentCard
    engine: AsyncEngine


def build_runtime(
    settings: WorkoutSettings,
    *,
    llm: LLMProvider | None = None,
    peers: PeerClient | None = None,
    memory: VectorMemory | None = None,
    clock: Clock | None = None,
) -> WorkoutRuntime:
    base = build_agent_base(settings, llm=llm, peers=peers, memory=memory, clock=clock)
    uow = SqlUnitOfWorkFactory(base.engine, base_repositories())

    def analysis(mode: str) -> AnalysisSkill:
        return AnalysisSkill(
            spec=WORKOUT_SPEC,
            mode=mode,
            data=WorkoutData(),
            llm=base.llm,
            uow=uow,
            peers=base.peers,
            memory=base.memory,
            clock=base.clock,
            translator=base.translator,
            default_locale=base.default_locale,
        )

    handlers: dict[str, SkillHandler] = {
        WorkoutSkill.LOG: LogWorkout(
            llm=base.llm,
            uow=uow,
            clock=base.clock,
            translator=base.translator,
            memory=base.memory,
            default_locale=base.default_locale,
        ),
        WorkoutSkill.ANALYZE: analysis(WorkoutSkill.ANALYZE),
        WorkoutSkill.RECOMMENDATIONS: analysis(WorkoutSkill.RECOMMENDATIONS),
    }
    dashboard_uow = uow
    routable = tuple(handlers)
    handlers[Dashboard.CARD] = DashboardSkill(
        uow=dashboard_uow, clock=base.clock, build=card, name=Dashboard.CARD
    )
    handlers[Dashboard.DETAIL] = DashboardSkill(
        uow=dashboard_uow, clock=base.clock, build=detail, name=Dashboard.DETAIL
    )
    return WorkoutRuntime(
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
        card=build_agent_card(settings.workout_agent_url),
        engine=base.engine,
    )
