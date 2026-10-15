import httpx
import pytest
from finance.composition import build_runtime
from finance.main import create_app
from finance.settings import FinanceSettings
from shared.adapters.a2a.skill_client import A2ASkillClient
from shared.skill_ids import Dashboard
from shared.testing import dashboard_golden as g
from shared.testing.fakes import FakeLLM, FixedClock
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


async def test_card_and_detail_over_sql_match_the_goldens(clean_db: PostgresUrls) -> None:
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        await g.seed_postgres(conn)
    await admin.dispose()
    runtime = build_runtime(
        FinanceSettings.model_validate({"database": {"dsn": clean_db.rw}}),
        llm=FakeLLM(),
        clock=FixedClock(g.FROZEN_NOW),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runtime)), base_url="http://agent"
    ) as http:
        client = A2ASkillClient("http://agent/", http)
        detail = await client.call(skill_id=Dashboard.DETAIL, user_id=g.USER_ID, params={})
    assert g.as_json(detail.data) == g.expected_detail("finance")
