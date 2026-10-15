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
from shared.feed import FeedSkill
from shared.ports.clock import Clock
from shared.ports.llm import LLMProvider
from shared.ports.peers import PeerClient
from shared.ports.vector_memory import VectorMemory
from shared.skill_ids import Dashboard, Feed, Habits
from sqlalchemy.ext.asyncio import AsyncEngine

from habits.adapters.a2a.card import PEER_SKILLS, build_agent_card
from habits.adapters.db import habits_repositories
from habits.application.archive import ArchiveHabit
from habits.application.check import CheckHabit
from habits.application.dashboard import card, detail
from habits.application.data import HabitData
from habits.application.define import DefineHabit
from habits.application.feed import collect as feed_collect
from habits.application.streaks import StreakSummary
from habits.settings import HabitsSettings

AGENT = "habits"
HABITS_SPEC = AnalysisSpec(
    agent=AGENT,
    tails={
        Habits.ANALYZE: (
            "Respond in 4–6 lines plain text: (1) per-habit completion %, (2) current streak and longest "
            "streak, (3) one observation linking to peer context (e.g. mood, sleep, training) if present. "
            "Redirect cross-domain prescriptions to peers. No markdown."
        ),
    },
    peer_order=("mood", "sleep", "workout"),
    peer_skills=PEER_SKILLS,
    memories=False,  # the legacy analyze_habit prompt had no memories
)


@dataclass(frozen=True, slots=True)
class HabitsRuntime:
    executor: SkillExecutor
    task_store: SqlTaskStore
    card: AgentCard
    engine: AsyncEngine


def build_runtime(
    settings: HabitsSettings,
    *,
    llm: LLMProvider | None = None,
    peers: PeerClient | None = None,
    memory: VectorMemory | None = None,
    clock: Clock | None = None,
) -> HabitsRuntime:
    base = build_agent_base(settings, llm=llm, peers=peers, memory=memory, clock=clock)
    uow = SqlUnitOfWorkFactory(base.engine, {**base_repositories(), **habits_repositories()})
    handlers: dict[str, SkillHandler] = {
        Habits.DEFINE: DefineHabit(
            llm=base.llm,
            uow=uow,
            clock=base.clock,
            translator=base.translator,
            memory=base.memory,
            default_locale=base.default_locale,
        ),
        Habits.LOG_CHECK: CheckHabit(
            llm=base.llm,
            uow=uow,
            clock=base.clock,
            translator=base.translator,
            memory=base.memory,
            default_locale=base.default_locale,
        ),
        Habits.ARCHIVE: ArchiveHabit(
            llm=base.llm,
            uow=uow,
            clock=base.clock,
            translator=base.translator,
            memory=base.memory,
            default_locale=base.default_locale,
        ),
        Habits.STREAK_SUMMARY: StreakSummary(
            uow=uow,
            clock=base.clock,
            translator=base.translator,
            default_locale=base.default_locale,
        ),
        Habits.ANALYZE: AnalysisSkill(
            spec=HABITS_SPEC,
            mode=Habits.ANALYZE,
            data=HabitData(),
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
    return HabitsRuntime(
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
        card=build_agent_card(settings.habits_agent_url),
        engine=base.engine,
    )
