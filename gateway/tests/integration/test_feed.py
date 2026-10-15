from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi import FastAPI
from gateway.auth.settings import AuthSettings
from gateway.composition import build_gateway
from gateway.feed import FEED_AGENTS
from gateway.settings import GatewaySettings
from shared.adapters.a2a.skill_client import A2ASkillClient
from shared.testing import dashboard_golden as g
from shared.testing.fakes import FixedClock
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy.ext.asyncio import create_async_engine

from .agents_harness import KEY, HostRouter, build_apps

pytestmark = pytest.mark.integration


class FeedTransport(HostRouter):
    """Model a stopped peer as a network failure, like an unavailable real host."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.host not in self._transports:
            raise httpx.ConnectError("peer_unavailable", request=request)
        return await super().handle_async_request(request)


async def _feed(clean_db: PostgresUrls, *, drop: str | None, user: UUID) -> dict:
    apps = build_apps(clean_db.rw)
    if drop:
        apps.pop(f"agent-{drop}")
    async with httpx.AsyncClient(transport=FeedTransport(apps)) as http:
        if user == g.USER_ID:
            await A2ASkillClient("http://agent-calendar:8012/", http).call(
                skill_id="calendar.connect",
                user_id=user,
                params={"code": "c", "code_verifier": "v"},
            )
        gateway = build_gateway(
            GatewaySettings.model_validate(
                {"database": {"dsn": clean_db.rw}, "secrets": {"key": KEY}}
            ),
            auth=AuthSettings(auth_mode="dev"),
            http=http,
            clock=FixedClock(g.FROZEN_NOW),
        )
        try:
            app = FastAPI()
            for router in gateway.routers:
                app.include_router(router)
            day = g.FROZEN_NOW.astimezone(ZoneInfo(g.TIMEZONE)).date().isoformat()
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://gateway"
            ) as client:
                response = await client.get(
                    f"/me/feed?date={day}", headers={"X-User-Id": str(user)}
                )
                assert response.status_code == 200
                return response.json()
        finally:
            await gateway.aclose()


async def test_feed_from_real_agents_with_one_stopped_and_tenant_isolation(
    clean_db: PostgresUrls,
) -> None:
    admin = create_async_engine(clean_db.admin)
    try:
        async with admin.begin() as conn:
            await g.seed_postgres(conn)
    finally:
        await admin.dispose()
    body = await _feed(clean_db, drop="mood", user=g.USER_ID)
    assert body["unavailable"] == ["mood"]
    assert body["items"]
    assert {i["agent"] for i in body["items"]} == set(FEED_AGENTS) - {"mood", "body"}
    stranger = await _feed(clean_db, drop=None, user=uuid4())
    assert stranger["items"] == []
    assert stranger["unavailable"] == []
