from datetime import date
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest
from recovery.composition import build_runtime
from recovery.main import create_app
from recovery.settings import RecoverySettings
from shared.adapters.a2a.skill_client import A2ASkillClient
from shared.skill_ids import Dashboard, Feed
from shared.testing import dashboard_golden as g
from shared.testing.fakes import FakeLLM, FakePeerClient, FixedClock, InMemoryVectorMemory
from shared.testing.feed_contract import assert_feed_contract
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


async def test_card_and_detail_over_sql_match_the_goldens(clean_db: PostgresUrls) -> None:
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        await g.seed_postgres(conn)
    await admin.dispose()
    runtime = build_runtime(
        RecoverySettings.model_validate({"database": {"dsn": clean_db.rw}}),
        llm=FakeLLM(),
        peers=FakePeerClient(),
        memory=InMemoryVectorMemory(),
        clock=FixedClock(g.FROZEN_NOW),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runtime)), base_url="http://agent"
    ) as http:
        client = A2ASkillClient("http://agent/", http)
        card = await client.call(skill_id=Dashboard.CARD, user_id=g.USER_ID, params={})
        detail = await client.call(skill_id=Dashboard.DETAIL, user_id=g.USER_ID, params={})
        feed = await client.call(skill_id=Feed.EVENTS, user_id=g.USER_ID, params={})
        other = await client.call(skill_id=Feed.EVENTS, user_id=uuid4(), params={})
    assert g.as_json(card.data) == g.expected_card("recovery")
    assert g.as_json(detail.data) == g.expected_detail("recovery")

    assert_feed_contract(feed.data, date(2026, 10, 14), ZoneInfo("Europe/Kyiv"))
    assert feed.data["items"]
    assert other.data == {"items": []}
