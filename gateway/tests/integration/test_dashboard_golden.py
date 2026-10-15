import httpx
import pytest
from fastapi import FastAPI
from gateway.composition import build_gateway
from gateway.settings import GatewaySettings
from shared.testing import dashboard_golden as g
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy.ext.asyncio import create_async_engine

from .agents_harness import KEY, HostRouter, build_apps

pytestmark = pytest.mark.integration


async def test_summary_and_details_from_the_real_agents_equal_the_goldens(
    clean_db: PostgresUrls, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        await g.seed_postgres(conn)
    await admin.dispose()
    apps = build_apps(clean_db.rw)
    # Calendar credentials: put them through the calendar agent's own store, under the user's tenant.
    async with httpx.AsyncClient(transport=HostRouter(apps)) as http:
        from shared.adapters.a2a.skill_client import A2ASkillClient

        await A2ASkillClient("http://agent-calendar:8012/", http).call(
            skill_id="calendar.connect",
            user_id=g.USER_ID,
            params={"code": "c", "code_verifier": "v"},
        )
        monkeypatch.setenv("AUTH_MODE", "dev")
        gateway = build_gateway(
            GatewaySettings.model_validate(
                {"database": {"dsn": clean_db.rw}, "secrets": {"key": KEY}}
            ),
            http=http,
        )
        app = FastAPI()
        for router in gateway.routers:
            app.include_router(router)
        headers = {"X-User-Id": str(g.USER_ID)}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway"
        ) as client:
            summary = (await client.get("/dashboard/summary", headers=headers)).json()
            details = {
                a: (await client.get(f"/agents/{a}/detail", headers=headers)).json()
                for a in g.DETAIL_AGENTS
            }
        await gateway.aclose()
    assert summary.pop("unavailable") == []
    assert summary == g.golden("dashboard_summary")
    for agent, data in details.items():
        assert data == g.golden(f"detail_{agent}"), agent


async def test_agent_counts_are_caller_scoped_since_local_midnight(clean_db: PostgresUrls) -> None:
    from datetime import UTC, datetime
    from uuid import uuid4

    from gateway.auth.settings import AuthSettings
    from shared.schema.tables import tasks, users
    from shared.testing.fakes import FixedClock
    from sqlalchemy import insert

    user, other = uuid4(), uuid4()
    now = datetime(2026, 10, 15, 1, tzinfo=UTC)
    admin = create_async_engine(clean_db.admin)
    try:
        async with admin.begin() as conn:
            await conn.execute(
                insert(users),
                [
                    {"id": user, "name": "caller", "timezone": "America/Los_Angeles"},
                    {"id": other, "name": "other", "timezone": "UTC"},
                ],
            )
            await conn.execute(
                insert(tasks),
                [
                    {"agent": "sleep", "input": {"user_id": str(owner)}, "created_at": created}
                    for owner, created in [
                        (user, datetime(2026, 10, 14, 7, tzinfo=UTC)),
                        (user, datetime(2026, 10, 14, 6, 59, tzinfo=UTC)),
                        (other, now),
                    ]
                ],
            )
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"skills": []}))
        ) as http:
            gateway = build_gateway(
                GatewaySettings.model_validate(
                    {"database": {"dsn": clean_db.rw}, "secrets": {"key": KEY}}
                ),
                auth=AuthSettings(auth_mode="dev"),
                clock=FixedClock(now),
                http=http,
            )
            try:
                app = FastAPI()
                for router in gateway.routers:
                    app.include_router(router)
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://gateway"
                ) as client:
                    response = await client.get("/agents", headers={"X-User-Id": str(user)})
                assert response.status_code == 200
                counts = {a["name"]: a["tasks_today"] for a in response.json()["agents"]}
                assert counts["sleep"] == 1
                assert counts["workout"] == 0
            finally:
                await gateway.aclose()
    finally:
        await admin.dispose()
