from __future__ import annotations

from collections.abc import Sequence

from shared.ports.translator import Translator

from finance.domain.figures import Transaction, income, spending, spending_by_category
from finance.domain.money import format_amount

TOP = 3


def render_import_summary(
    tr: Translator, locale: str, *, inserted: int, skipped: int, rows: Sequence[Transaction]
) -> str:
    lines = [tr.t("finance.import.done", locale, inserted=inserted, skipped=skipped)]
    got = income(rows)
    if got:
        items = ", ".join(format_amount(c, v, sign="+") for c, v in sorted(got.items()))
        lines.append(tr.t("finance.import.income", locale, items=items))
    spent = spending(rows)
    if spent:
        items = ", ".join(format_amount(c, v, sign="−") for c, v in sorted(spent.items()))
        lines.append(tr.t("finance.import.spending", locale, items=items))
    top = spending_by_category(rows)[:TOP]
    if top:
        items = " · ".join(f"{cat} {format_amount(cur, amount)}" for cat, cur, amount in top)
        lines.append(tr.t("finance.import.top", locale, items=items))
    return "\n".join(lines)
