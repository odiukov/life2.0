from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest
from shared.adapters.a2a.skill_client import A2ASkillClient
from shared.skill_ids import Feed
from shared.testing import dashboard_golden as g
from shared.testing.feed_contract import assert_feed_contract
from shared.testing.pytest_plugin import PostgresUrls
from sleep.main import create_app
from sqlalchemy.ext.asyncio import create_async_engine

from agents.sleep.tests.integration.test_dashboard_sql import build_sleep_runtime

pytestmark = pytest.mark.integration


async def test_feed_reads_the_golden_week_under_rls(clean_db: PostgresUrls) -> None:
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        await g.seed_postgres(conn)
    await admin.dispose()
    runtime = build_sleep_runtime(clean_db.rw)
    zone = ZoneInfo(g.TIMEZONE)
    today = g.FROZEN_NOW.astimezone(zone).date()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(runtime)), base_url="http://agent"
        ) as http:
            client = A2ASkillClient("http://agent/", http)
            mine = await client.call(
                skill_id=Feed.EVENTS, user_id=g.USER_ID, params={"date": today.isoformat()}
            )
            assert_feed_contract(mine.data, today, zone)
            assert any(i["kind"] == "event" for i in mine.data["items"])
            theirs = await client.call(
                skill_id=Feed.EVENTS, user_id=uuid4(), params={"date": today.isoformat()}
            )
            assert theirs.data == {"items": []}
    finally:
        await runtime.engine.dispose()
