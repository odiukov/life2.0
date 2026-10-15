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
from shared.skill_ids import Finance
from sqlalchemy.ext.asyncio import AsyncEngine

from finance.adapters.a2a.card import build_agent_card
from finance.adapters.db import finance_repositories
from finance.adapters.pdf import PymupdfText
from finance.application.categorize import Categorizer
from finance.application.data import FinanceData
from finance.application.import_statement import ImportStatement
from finance.application.ports import PdfText
from finance.settings import FinanceSettings

AGENT = "finance"
FINANCE_SPEC = AnalysisSpec(
    agent=AGENT,
    tails={
        Finance.ASK: (
            "Answer the user's question in 2–6 lines of plain text using ONLY the figures above. "
            "Quote every amount with its currency and never convert currencies. If the question "
            "needs a month or a figure that is not above, say which statement is missing. No markdown."
        )
    },
    peer_order=(),
    peer_skills={},
    memories=False,
)


@dataclass(frozen=True, slots=True)
class FinanceRuntime:
    executor: SkillExecutor
    task_store: SqlTaskStore
    card: AgentCard
    engine: AsyncEngine


def build_runtime(
    settings: FinanceSettings,
    *,
    llm: LLMProvider | None = None,
    clock: Clock | None = None,
    pdf: PdfText | None = None,
) -> FinanceRuntime:
    base = build_agent_base(settings, llm=llm, clock=clock)
    uow = SqlUnitOfWorkFactory(base.engine, {**base_repositories(), **finance_repositories()})
    handlers: dict[str, SkillHandler] = {
        Finance.ASK: AnalysisSkill(
            spec=FINANCE_SPEC,
            mode=Finance.ASK,
            data=FinanceData(translator=base.translator, default_locale=base.default_locale),
            llm=base.llm,
            uow=uow,
            peers=base.peers,
            memory=base.memory,
            clock=base.clock,
            translator=base.translator,
            default_locale=base.default_locale,
        ),
        Finance.IMPORT_STATEMENT: ImportStatement(
            pdf=pdf or PymupdfText(),
            uow=uow,
            categorize=Categorizer(llm=base.llm, uow=uow),
            clock=base.clock,
            translator=base.translator,
            default_locale=base.default_locale,
        ),
    }
    return FinanceRuntime(
        executor=SkillExecutor(
            agent=AGENT,
            handlers=handlers,
            peers=[],
            llm=base.llm,
            task_records=base.task_records,
            clock=base.clock,
            routable=[Finance.ASK],
        ),
        task_store=SqlTaskStore(base.engine, agent=AGENT),
        card=build_agent_card(settings.finance_agent_url),
        engine=base.engine,
    )
