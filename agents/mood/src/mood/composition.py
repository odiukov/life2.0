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
from shared.skill_ids import Attention, Dashboard, Feed, Mood
from sqlalchemy.ext.asyncio import AsyncEngine

from mood.adapters.a2a.card import PEER_SKILLS, build_agent_card
from mood.application.attention import collect as attention_collect
from mood.application.coach_session import CoachSession
from mood.application.dashboard import card, detail
from mood.application.data import MoodData
from mood.application.feed import collect as feed_collect
from mood.application.log_mood import LogMood
from mood.settings import MoodSettings

AGENT = "mood"
MOOD_SPEC = AnalysisSpec(
    agent=AGENT,
    tails={
        Mood.ANALYZE: (
            "Respond in 6–10 lines plain text: (1) 7-day trend (score/energy/stress) grounded in the "
            "data, (2) dominant valence + top 3 tags, (3) one mechanism (e.g. mood–energy decoupling, "
            "diurnal pattern). Redirect cross-domain prescriptions to peers. No markdown."
        ),
        Mood.RECOMMENDATIONS: (
            "Respond in 4–6 lines plain text with 2–3 concrete mood-domain actions + the 'why' grounded "
            "in the recent pattern. Redirect training, sleep, or medication asks to the relevant peer. "
            "No markdown."
        ),
    },
    peer_order=("sleep", "recovery", "workout", "habits", "medication"),
    peer_skills=PEER_SKILLS,
)


@dataclass(frozen=True, slots=True)
class MoodRuntime:
    executor: SkillExecutor
    task_store: SqlTaskStore
    card: AgentCard
    engine: AsyncEngine


def build_runtime(
    settings: MoodSettings,
    *,
    llm: LLMProvider | None = None,
    peers: PeerClient | None = None,
    memory: VectorMemory | None = None,
    clock: Clock | None = None,
) -> MoodRuntime:
    base = build_agent_base(settings, llm=llm, peers=peers, memory=memory, clock=clock)
    uow = SqlUnitOfWorkFactory(base.engine, base_repositories())

    def analysis(mode: str) -> AnalysisSkill:
        return AnalysisSkill(
            spec=MOOD_SPEC,
            mode=mode,
            data=MoodData(mode),
            llm=base.llm,
            uow=uow,
            peers=base.peers,
            memory=base.memory,
            clock=base.clock,
            translator=base.translator,
            default_locale=base.default_locale,
        )

    handlers: dict[str, SkillHandler] = {
        Mood.LOG: LogMood(
            llm=base.llm,
            uow=uow,
            clock=base.clock,
            translator=base.translator,
            memory=base.memory,
            default_locale=base.default_locale,
        ),
        Mood.ANALYZE: analysis(Mood.ANALYZE),
        Mood.RECOMMENDATIONS: analysis(Mood.RECOMMENDATIONS),
        Mood.COACH_SESSION: CoachSession(
            llm=base.llm,
            uow=uow,
            clock=base.clock,
            translator=base.translator,
            memory=base.memory,
            default_locale=base.default_locale,
        ),
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
    handlers[Attention.ITEMS] = AttentionSkill(
        uow=dashboard_uow,
        clock=base.clock,
        translator=base.translator,
        default_locale=base.default_locale,
        collect=attention_collect,
    )
    return MoodRuntime(
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
        card=build_agent_card(settings.mood_agent_url),
        engine=base.engine,
    )
