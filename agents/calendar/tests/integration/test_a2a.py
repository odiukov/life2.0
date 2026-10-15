import base64
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from calendar_agent.composition import build_runtime
from calendar_agent.main import create_app
from calendar_agent.settings import CalendarSettings
from calendar_agent.testing import FakeGoogleCalendar, FakeGoogleOAuth
from shared.adapters.a2a.skill_client import A2ASkillClient
from shared.ports.skills import SkillCallError
from shared.testing.dashboard_golden import GOOGLE_EVENTS
from shared.testing.fakes import FixedClock
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration
KEY = base64.b64encode(bytes(range(32))).decode()


async def test_connect_list_and_isolation(clean_db: PostgresUrls) -> None:
    me, other = uuid4(), uuid4()
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, name, timezone) VALUES (:a, 'a', 'Europe/Kyiv'), (:b, 'b', 'UTC')"
            ),
            {"a": me, "b": other},
        )
    runtime = build_runtime(
        CalendarSettings.model_validate(
            {"database": {"dsn": clean_db.rw}, "secrets": {"key": KEY}}
        ),
        google=FakeGoogleCalendar(GOOGLE_EVENTS),
        oauth=FakeGoogleOAuth(),
        clock=FixedClock(datetime(2026, 10, 14, 6, 30, tzinfo=UTC)),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runtime)), base_url="http://calendar"
    ) as http:
        client = A2ASkillClient("http://calendar/", http)
        await client.call(
            skill_id="calendar.connect", user_id=me, params={"code": "c", "code_verifier": "v"}
        )
        listed = await client.call(
            skill_id="calendar.list", user_id=me, params={"day": "2026-10-14"}
        )
        with pytest.raises(SkillCallError) as error:
            await client.call(skill_id="calendar.list", user_id=other, params={"day": "2026-10-14"})
        with pytest.raises(SkillCallError) as free_text:
            await client.call(skill_id="", user_id=me, params={}, text="what is on today?")
    async with admin.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT payload_dev, payload_enc FROM integrations_credentials WHERE user_id=:u"
                ),
                {"u": me},
            )
        ).one()
    await admin.dispose()
    assert len(listed.data["events"]) == 4
    assert error.value.code == "not_connected"
    assert free_text.value.code == "cannot determine skill"
    assert row.payload_dev is None
    assert b"refresh-1" not in bytes(row.payload_enc)
