from datetime import UTC, datetime
from uuid import uuid4

import pytest
from finance.application.categorize import Categorizer, CategoryBatch, CategoryChoice
from finance.application.import_statement import ImportStatement
from finance.testing import FakePdfText, InMemoryCategoryCache, InMemoryTransactions, in_memory_uow
from finance_fixtures import NOT_A_STATEMENT, STATEMENT
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.config import find_locales_dir
from shared.ports.llm import LLMUnavailable
from shared.ports.skills import Attachment
from shared.testing.fakes import FakeLLM, FixedClock, InMemoryUserSettings

NOW = datetime(2026, 11, 2, 9, tzinfo=UTC)
PDF = Attachment(name="oct.pdf", mime="application/pdf", data=b"%PDF-1.7 fake")


def request(user, *attachments: Attachment) -> SkillRequest:
    return SkillRequest(
        task_id="t1",
        context_id="c1",
        text="",
        user_id=user,
        skill_id="finance.import_statement",
        for_date=None,
        is_peer_call=False,
        attachments=attachments,
    )


SETTINGS = InMemoryUserSettings()


def setup(text: str = STATEMENT, llm: FakeLLM | None = None):
    transactions, cache = InMemoryTransactions(), InMemoryCategoryCache()
    uow = in_memory_uow(transactions, cache, SETTINGS)
    llm = llm or FakeLLM()
    skill = ImportStatement(
        pdf=FakePdfText(text),
        uow=uow,
        categorize=Categorizer(llm=llm, uow=uow),
        clock=FixedClock(NOW),
        translator=JsonTranslator.from_dir(find_locales_dir()),
        default_locale="en",
    )
    return skill, transactions, cache, llm


def batch(**pairs: str) -> CategoryBatch:
    return CategoryBatch(
        items=[CategoryChoice(key=k.replace("_", "-"), category=v) for k, v in pairs.items()]
    )


async def test_import_stores_categorizes_and_summarizes() -> None:
    skill, transactions, cache, llm = setup()
    llm.queue_structured(
        batch(
            client_payment_acme="income",
            rent_october="housing",
            pingo_doce="food",
            netflix="subscriptions",
        )
    )
    user = uuid4()
    result = await skill(request(user, PDF), ())
    assert not result.failed
    assert result.data == {"inserted": 4, "skipped": 1, "months": ["2026-10"]}
    rows = await transactions.all(user)
    assert {r.category for r in rows} == {"income", "housing", "food", "subscriptions"}
    assert cache.rows[user]["netflix"] == "subscriptions"
    assert "4 new" in result.output
    assert "+$4 000.00 USD" in result.output
    assert "−$1 261.49 USD" in result.output  # every outgoing row counts, categorized or not
    assert len(llm.calls) == 1


async def test_reimporting_a_statement_is_idempotent() -> None:
    skill, transactions, _cache, llm = setup()
    llm.queue_structured(
        batch(
            client_payment_acme="income",
            rent_october="housing",
            pingo_doce="food",
            netflix="subscriptions",
        )
    )
    user = uuid4()
    await skill(request(user, PDF), ())
    second = await skill(request(user, PDF), ())
    assert second.data == {"inserted": 0, "skipped": 5, "months": ["2026-10"]}
    assert len(await transactions.all(user)) == 4
    assert len(llm.calls) == 1  # nothing new to categorize, cache untouched
    assert "0 new" in second.output


async def test_failed_categorization_leaves_rows_for_the_next_upload() -> None:
    llm = FakeLLM()
    llm.queue_structured(LLMUnavailable("down"))
    skill, transactions, _, llm = setup(llm=llm)
    user = uuid4()
    first = await skill(request(user, PDF), ())
    assert not first.failed
    assert all(r.category is None for r in await transactions.all(user))
    llm.queue_structured(
        batch(
            client_payment_acme="income", rent_october="housing", pingo_doce="food", netflix="other"
        )
    )
    await skill(request(user, PDF), ())
    assert all(r.category for r in await transactions.all(user))


async def test_cache_hits_skip_the_model() -> None:
    skill, _, cache, llm = setup()
    user = uuid4()
    cache.rows[user] = {
        "client-payment-acme": "income",
        "rent-october": "housing",
        "pingo-doce": "food",
        "netflix": "other",
    }
    await skill(request(user, PDF), ())
    assert llm.calls == []


async def test_unknown_categories_and_keys_from_the_model_are_ignored() -> None:
    skill, transactions, _, llm = setup()
    llm.queue_structured(
        CategoryBatch(
            items=[
                CategoryChoice(key="netflix", category="subscriptions"),
                CategoryChoice(key="made-up", category="food"),
            ]
        )
    )
    user = uuid4()
    await skill(request(user, PDF), ())
    by_desc = {r.description: r.category for r in await transactions.all(user)}
    assert by_desc["Netflix 9981"] == "subscriptions"
    assert by_desc["Rent October"] is None


@pytest.mark.parametrize(
    ("attachments", "code"),
    [
        ((), "invalid_params"),
        ((PDF, PDF), "invalid_params"),
        ((Attachment(name="x.png", mime="image/png", data=b"\x89PNG"),), "invalid_params"),
        ((Attachment(name="x.pdf", mime="application/pdf", data=b"garbage"),), "unreadable_pdf"),
    ],
)
async def test_bad_uploads_fail_with_codes(attachments, code) -> None:
    skill, *_ = setup()
    result = await skill(request(uuid4(), *attachments), ())
    assert result.failed
    assert result.output == code


async def test_other_documents_are_not_statements() -> None:
    skill, *_ = setup(text=NOT_A_STATEMENT)
    result = await skill(request(uuid4(), PDF), ())
    assert result.failed
    assert result.output == "not_a_statement"


async def test_english_summary_for_english_users() -> None:
    skill, _, _, llm = setup()
    llm.queue_structured(
        batch(
            client_payment_acme="income",
            rent_october="housing",
            pingo_doce="food",
            netflix="subscriptions",
        )
    )
    user = uuid4()
    SETTINGS.seed(user, timezone="Europe/Lisbon", locale="en")
    result = await skill(request(user, PDF), ())
    assert result.output.splitlines()[0] == "✓ Statement imported (4 new, 1 skipped)"
    assert "Income: +$4 000.00 USD" in result.output
