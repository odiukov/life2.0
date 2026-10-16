from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from gateway.auth.settings import AuthSettings
from gateway.composition import build_gateway
from gateway.settings import GatewaySettings
from kitchen.application.schema import AddItem, OperationList
from kitchen.composition import build_runtime as kitchen_runtime
from kitchen.domain.model import Category, Location, Source
from kitchen.domain.units import InputUnit
from kitchen.main import create_app as kitchen_app
from kitchen.settings import KitchenSettings
from shared.schema.tables import health_logs, users
from shared.testing import dashboard_golden as g
from shared.testing.fakes import FakeLLM, FakeNotificationSender, FakeScheduler, FixedClock
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import create_async_engine

from .agents_harness import KEY, HostRouter, build_apps

pytestmark = pytest.mark.integration

NOW = g.FROZEN_NOW  # 2026-10-14 09:30 in Kyiv


class StoppedPeers(HostRouter):
    """Model a stopped peer as a network failure, like an unavailable real host."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.host not in self._transports:
            raise httpx.ConnectError("peer_unavailable", request=request)
        return await super().handle_async_request(request)


async def _seed(clean_db: PostgresUrls, user: UUID) -> None:
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        await conn.execute(insert(users).values(id=user, name="Attn", timezone=g.TIMEZONE))
        await conn.execute(
            insert(health_logs),
            [
                {
                    "user_id": user,
                    "agent": "workout",
                    "type": "activity",
                    "source": "garmin",
                    "recorded_at": datetime(2026, 10, day, 8, tzinfo=UTC),
                    "data": {"activity_type": "running", "name": "Run", "duration_seconds": 1800},
                }
                for day in (5, 6)
            ],
        )
    await admin.dispose()
    rw = create_async_engine(clean_db.rw)
    async with rw.begin() as conn:
        await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user)})
        await conn.execute(text("SELECT household_ensure('Аня', :tz)"), {"tz": g.TIMEZONE})
    await rw.dispose()


def _add(name: str, expires_on: date) -> AddItem:
    return AddItem(
        name=name,
        display_name=name,
        quantity=1,
        unit=InputUnit.KG,
        location=Location.FRIDGE,
        category=Category.MEAT,
        expires_on=expires_on,
    )


@asynccontextmanager
async def _gateway(clean_db: PostgresUrls, user: UUID) -> AsyncIterator[httpx.AsyncClient]:
    clock = FixedClock(NOW)
    kitchen = kitchen_runtime(
        KitchenSettings.model_validate({"database": {"dsn": clean_db.rw}}),
        llm=FakeLLM(),
        clock=clock,
        scheduler=FakeScheduler(),
        sender=FakeNotificationSender(),
    )
    await kitchen.service.apply(
        user,
        ops=OperationList(
            adds=[_add("курица", date(2026, 10, 12)), _add("молоко", date(2026, 10, 14))]
        ),
        refs={},
        source=Source.TEXT,
    )
    apps = build_apps(clean_db.rw)
    apps.pop("agent-sleep")
    apps["agent-kitchen"] = kitchen_app(kitchen)
    async with httpx.AsyncClient(transport=StoppedPeers(apps)) as http:
        gateway = build_gateway(
            GatewaySettings.model_validate(
                {"database": {"dsn": clean_db.rw}, "secrets": {"key": KEY}}
            ),
            auth=AuthSettings(auth_mode="dev"),
            http=http,
            clock=clock,
        )
        try:
            app = FastAPI()
            for router in gateway.routers:
                app.include_router(router)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://gateway"
            ) as client:
                yield client
        finally:
            await gateway.aclose()


async def test_attention_from_real_agents_dismiss_and_tenant_isolation(
    clean_db: PostgresUrls,
) -> None:
    user, stranger = uuid4(), uuid4()
    await _seed(clean_db, user)
    async with _gateway(clean_db, user) as client:
        h = {"X-User-Id": str(user)}
        body = (await client.get("/me/attention", headers=h)).json()
        assert body["unavailable"] == ["sleep"]
        assert [(i["agent"], i["level"]) for i in body["items"]] == [
            ("kitchen", "critical"),
            ("workout", "high"),
            ("kitchen", "high"),
            ("nutrition", "high"),  # no body profile yet
        ]
        today_id = body["items"][2]["id"]
        assert today_id == "kitchen:today:2026-10-14"
        critical = body["items"][0]["id"]
        assert (
            await client.post(f"/me/attention/{critical}/dismiss", headers=h)
        ).status_code == 409
        assert (
            await client.post(f"/me/attention/{today_id}/dismiss", headers=h)
        ).status_code == 204
        after = (await client.get("/me/attention", headers=h)).json()
        assert [i["id"] for i in after["items"]] == [
            critical,
            body["items"][1]["id"],
            "nutrition:profile",
        ]
        other = (await client.get("/me/attention", headers={"X-User-Id": str(stranger)})).json()
        assert [i["id"] for i in other["items"]] == [
            "nutrition:profile"
        ]  # own, not the first user's
    rw = create_async_engine(clean_db.rw)
    async with rw.begin() as conn:
        await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(stranger)})
        count = await conn.scalar(text("SELECT count(*) FROM attention_dismissals"))
    await rw.dispose()
    assert count == 0
