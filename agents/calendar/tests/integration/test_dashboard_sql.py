import base64

import httpx
import pytest
from calendar_agent.application.tokens import SERVICE
from calendar_agent.composition import build_runtime
from calendar_agent.main import create_app
from calendar_agent.settings import CalendarSettings
from calendar_agent.testing import FakeGoogleCalendar, FakeGoogleOAuth
from shared.adapters.a2a.skill_client import A2ASkillClient
from shared.adapters.db.credentials import sql_credential_store
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.adapters.secrets import AesGcmSecretBox
from shared.ports.credentials import CredentialStore
from shared.skill_ids import Dashboard
from shared.testing import dashboard_golden as g
from shared.testing.fakes import FixedClock
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


async def test_card_and_detail_over_sql_match_the_goldens(clean_db: PostgresUrls) -> None:
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        await g.seed_postgres(conn)
    await admin.dispose()
    settings = CalendarSettings.model_validate(
        {
            "database": {"dsn": clean_db.rw},
            "secrets": {"key": base64.b64encode(bytes(range(32))).decode()},
        }
    )
    runtime = build_runtime(
        settings,
        google=FakeGoogleCalendar(g.GOOGLE_EVENTS),
        oauth=FakeGoogleOAuth(),
        clock=FixedClock(g.FROZEN_NOW),
    )
    uow = SqlUnitOfWorkFactory(
        runtime.engine,
        {CredentialStore: sql_credential_store(AesGcmSecretBox.from_settings(settings.secrets))},
    )
    async with uow.for_user(g.USER_ID) as tx:
        await tx.repo(CredentialStore).put(
            g.USER_ID,
            SERVICE,
            {"access_token": "a", "refresh_token": "r", "expires_at": "2026-10-14T08:00:00Z"},
        )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runtime)), base_url="http://agent"
    ) as http:
        client = A2ASkillClient("http://agent/", http)
        card = await client.call(skill_id=Dashboard.CARD, user_id=g.USER_ID, params={})
        detail = await client.call(skill_id=Dashboard.DETAIL, user_id=g.USER_ID, params={})
    assert g.as_json(card.data) == g.expected_card("calendar")
    assert g.as_json(detail.data) == g.expected_detail("calendar")
