from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from finance.application.data import FinanceData
from finance.domain.statement import StatementRow
from finance.testing import InMemoryTransactions, in_memory_uow
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.config import find_locales_dir
from shared.ports.users import UserSettings

NOW = datetime(2026, 10, 14, 9, tzinfo=UTC)
TR = JsonTranslator.from_dir(find_locales_dir())


def req(user) -> SkillRequest:
    return SkillRequest("t", "c", "how much did I spend?", user, "finance.ask", None, False)


async def test_sections_hold_the_computed_figures() -> None:
    user = uuid4()
    transactions = InMemoryTransactions()
    await transactions.add_new(
        user,
        [
            StatementRow(
                "a", datetime(2026, 10, 1, tzinfo=UTC), "IN", Decimal("4000"), "USD", "Pay", {}
            ),
            StatementRow(
                "b", datetime(2026, 10, 3, tzinfo=UTC), "OUT", Decimal("1200"), "USD", "Rent", {}
            ),
            StatementRow(
                "c", datetime(2026, 9, 20, tzinfo=UTC), "OUT", Decimal("300"), "USD", "Trip", {}
            ),
        ],
    )
    await transactions.set_categories(user, {"b": "housing", "c": "travel"})
    data = FinanceData(translator=TR, default_locale="ru")
    uow = in_memory_uow(transactions)
    async with uow.for_user(user) as tx:
        loaded = await data.load(tx, req(user), UserSettings(ZoneInfo("Europe/Kyiv"), "en"), NOW)
    text = "\n".join(s.render() for s in loaded.sections)
    assert "2026-10" in text
    assert "USD: income 4000.00, spending 1200.00" in text
    assert "2026-09" in text
    assert "travel USD 300.00" in text
    assert "balance 2500.00" in text
    assert loaded.answer is None


async def test_no_transactions_answers_without_the_model() -> None:
    user = uuid4()
    data = FinanceData(translator=TR, default_locale="ru")
    async with in_memory_uow().for_user(user) as tx:
        loaded = await data.load(tx, req(user), UserSettings(ZoneInfo("UTC"), None), NOW)
    assert loaded.answer == TR.t("finance.ask.empty", "ru")
