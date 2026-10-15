from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from finance.application.categorize import CategoryBatch, CategoryChoice
from finance.composition import build_runtime
from finance.main import create_app
from finance.settings import FinanceSettings
from finance_fixtures import pdf_from
from shared.adapters.a2a.skill_client import A2ASkillClient
from shared.ports.skills import Attachment, SkillCallError
from shared.testing.fakes import FakeLLM, FixedClock
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


async def test_import_through_a2a_is_tenant_scoped_and_idempotent(clean_db: PostgresUrls) -> None:
    me, other = uuid4(), uuid4()
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, name, timezone) VALUES (:a, 'a', 'Europe/Kyiv'), (:b, 'b', 'UTC')"
            ),
            {"a": me, "b": other},
        )
    llm = FakeLLM()
    llm.queue_structured(
        CategoryBatch(
            items=[
                CategoryChoice(key="client-payment-acme", category="income"),
                CategoryChoice(key="rent-october", category="housing"),
                CategoryChoice(key="pingo-doce", category="food"),
                CategoryChoice(key="netflix", category="subscriptions"),
            ]
        )
    )  # one batch: the second import finds nothing uncategorized and must not call the model
    runtime = build_runtime(
        FinanceSettings.model_validate({"database": {"dsn": clean_db.rw}}),
        llm=llm,
        clock=FixedClock(datetime(2026, 11, 2, tzinfo=UTC)),
    )
    app = create_app(runtime)
    pdf = Attachment(name="oct.pdf", mime="application/pdf", data=pdf_from())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://finance"
    ) as http:
        client = A2ASkillClient("http://finance/", http)
        first = await client.call(
            skill_id="finance.import_statement", user_id=me, params={}, attachments=[pdf]
        )
        second = await client.call(
            skill_id="finance.import_statement", user_id=me, params={}, attachments=[pdf]
        )
        with pytest.raises(SkillCallError) as error:
            await client.call(skill_id="finance.import_statement", user_id=me, params={})
    assert first.data == {"inserted": 4, "skipped": 1, "months": ["2026-10"]}
    assert second.data == {"inserted": 0, "skipped": 5, "months": ["2026-10"]}
    assert error.value.code == "invalid_params"
    async with admin.begin() as conn:
        mine = (
            await conn.execute(
                text("SELECT count(*) FROM finance_transactions WHERE user_id=:u"), {"u": me}
            )
        ).scalar_one()
        theirs = (
            await conn.execute(
                text("SELECT count(*) FROM finance_transactions WHERE user_id=:u"), {"u": other}
            )
        ).scalar_one()
        netflix = (
            await conn.execute(
                text("SELECT category FROM finance_transactions WHERE description LIKE 'Netflix%'")
            )
        ).scalar_one()
    await admin.dispose()
    assert (mine, theirs, netflix) == (4, 0, "subscriptions")
    assert len(llm.calls) == 1
