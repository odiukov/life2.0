"""Composition root: the only place that chooses adapters."""

from __future__ import annotations

from dataclasses import dataclass

from a2a.types import AgentCard
from shared.a2a.executor import SkillExecutor, SkillHandler
from shared.adapters.a2a.task_store import SqlTaskStore
from shared.adapters.agent_base import base_repositories, build_agent_base
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.analysis.skill import AnalysisSkill, AnalysisSpec, previous_day
from shared.dashboard import DashboardSkill
from shared.feed import FeedSkill
from shared.ports.clock import Clock
from shared.ports.llm import LLMProvider
from shared.ports.peers import PeerClient
from shared.ports.vector_memory import VectorMemory
from shared.skill_ids import Dashboard, Feed, Sleep
from sqlalchemy.ext.asyncio import AsyncEngine

from sleep.adapters.a2a.card import PEER_SKILLS, build_agent_card
from sleep.application.dashboard import card, detail
from sleep.application.data import SleepData
from sleep.application.feed import collect as feed_collect
from sleep.application.log_sleep import LogSleep
from sleep.settings import SleepSettings

AGENT = "sleep"
SLEEP_SPEC = AnalysisSpec(
    agent=AGENT,
    tails={
        Sleep.ANALYZE: (
            "Respond in 6–10 lines plain text: (1) the sleep observation grounded "
            "in the data, (2) one mechanism explaining it, (3) one sentence on "
            "expected impact for today. No markdown."
        ),
        Sleep.RECOMMENDATIONS: (
            "Respond in 4–6 lines plain text: 2–3 concrete sleep-domain actions "
            "for tonight + a one-line 'why' tied to the data. Redirect "
            "cross-domain asks (meal timing → /nutrition, training timing → "
            "/workout). No markdown."
        ),
    },
    peer_order=("workout", "nutrition", "recovery", "mood", "medication"),
    peer_skills=PEER_SKILLS,
    peer_date=previous_day,
)


@dataclass(frozen=True, slots=True)
class SleepRuntime:
    executor: SkillExecutor
    task_store: SqlTaskStore
    card: AgentCard
    engine: AsyncEngine


def build_runtime(
    settings: SleepSettings,
    *,
    llm: LLMProvider | None = None,
    peers: PeerClient | None = None,
    memory: VectorMemory | None = None,
    clock: Clock | None = None,
) -> SleepRuntime:
    base = build_agent_base(settings, llm=llm, peers=peers, memory=memory, clock=clock)
    uow = SqlUnitOfWorkFactory(base.engine, base_repositories())

    def analysis(mode: str) -> AnalysisSkill:
        return AnalysisSkill(
            spec=SLEEP_SPEC,
            mode=mode,
            data=SleepData(),
            llm=base.llm,
            uow=uow,
            peers=base.peers,
            memory=base.memory,
            clock=base.clock,
            translator=base.translator,
            default_locale=base.default_locale,
        )

    handlers: dict[str, SkillHandler] = {
        Sleep.LOG: LogSleep(
            llm=base.llm,
            uow=uow,
            clock=base.clock,
            translator=base.translator,
            memory=base.memory,
            default_locale=base.default_locale,
        ),
        Sleep.ANALYZE: analysis(Sleep.ANALYZE),
        Sleep.RECOMMENDATIONS: analysis(Sleep.RECOMMENDATIONS),
    }
    dashboard_uow = uow
    routable = tuple(handlers)
    handlers[Dashboard.CARD] = DashboardSkill(
        uow=dashboard_uow, clock=base.clock, build=card, name=Dashboard.CARD
    )
    handlers[Dashboard.DETAIL] = DashboardSkill(
        uow=dashboard_uow, clock=base.clock, build=detail, name=Dashboard.DETAIL
    )
    handlers[Feed.EVENTS] = FeedSkill(
        uow=dashboard_uow,
        clock=base.clock,
        translator=base.translator,
        default_locale=base.default_locale,
        collect=feed_collect,
    )
    return SleepRuntime(
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
        card=build_agent_card(settings.sleep_agent_url),
        engine=base.engine,
    )
