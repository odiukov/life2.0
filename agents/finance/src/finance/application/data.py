"""What finance.ask puts in front of the model: figures computed here, never by the model."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from shared.a2a.request import SkillRequest
from shared.analysis.prompt import PromptSection
from shared.analysis.skill import AnalysisData, LoadedData
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWork
from shared.ports.users import UserSettings

from finance.application.ports import TransactionRepository
from finance.domain.figures import (
    Transaction,
    income,
    month_bounds,
    runway,
    spending,
    spending_by_category,
)

WINDOW_DAYS = 30


def _month_block(month: str, rows: Sequence[Transaction]) -> PromptSection:
    got, spent = income(rows), spending(rows)
    currencies = sorted(set(got) | set(spent))
    lines = [
        f"- {c}: income {got.get(c, 0):.2f}, spending {spent.get(c, 0):.2f}" for c in currencies
    ]
    lines += [f"- {cat} {cur} {amount}" for cat, cur, amount in spending_by_category(rows)]
    return PromptSection(
        f"Month {month} (income, spending, spending by category)",
        "\n".join(lines) or "No transactions.",
    )


class FinanceData(AnalysisData):
    def __init__(self, *, translator: Translator, default_locale: str) -> None:
        self._tr = translator
        self._default_locale = default_locale

    async def load(
        self, uow: UnitOfWork, request: SkillRequest, settings: UserSettings, now: datetime
    ) -> LoadedData:
        repo = uow.repo(TransactionRepository)
        everything = await repo.all(request.user_id)
        if not everything:
            locale = settings.locale or self._default_locale
            return LoadedData([], answer=self._tr.t("finance.ask.empty", locale))
        this_month = settings.today(now).strftime("%Y-%m")
        first = settings.today(now).replace(day=1)
        last_month = (first - timedelta(days=1)).strftime("%Y-%m")
        sections = []
        for month in (this_month, last_month):
            start, end = month_bounds(month, settings.timezone)
            sections.append(_month_block(month, [t for t in everything if start <= t.ts < end]))
        window = [t for t in everything if t.ts >= now - timedelta(days=WINDOW_DAYS)]
        lines = [
            f"- {c}: balance {r.balance}, average daily spending {r.avg_daily_burn}, "
            + (f"runway {r.days} days" if r.days is not None else "no spending in the last 30 days")
            for c, r in sorted(runway(everything, window, WINDOW_DAYS).items())
        ]
        sections.append(
            PromptSection("Balance and runway (all statements so far)", "\n".join(lines))
        )
        return LoadedData(sections)
