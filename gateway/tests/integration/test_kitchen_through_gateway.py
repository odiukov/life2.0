"""The app's /kitchen routes, through the real A2A skill client, into a real kitchen agent."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI, Header
from gateway.kitchen import KitchenGateway, build_router
from kitchen.application.schema import AddItem, OperationList
from kitchen.composition import build_runtime
from kitchen.domain.model import Category, Location, Source
from kitchen.domain.units import InputUnit
from kitchen.main import create_app
from kitchen.settings import KitchenSettings
from shared.adapters.a2a.skill_client import A2ASkillClient
from shared.testing.fakes import FakeLLM, FixedClock
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


async def dev_user(x_user_id: str = Header(alias="X-User-Id")) -> UUID:
    return UUID(x_user_id)


async def test_screen_flow(clean_db: PostgresUrls) -> None:
    user = uuid4()
    rw = create_async_engine(clean_db.rw)
    async with rw.begin() as conn:
        await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user)})
        await conn.execute(text("SELECT household_ensure('Аня', 'Europe/Lisbon')"))
    await rw.dispose()
    llm = FakeLLM()
    runtime = build_runtime(
        KitchenSettings.model_validate({"database": {"dsn": clean_db.rw}}),
        llm=llm,
        clock=FixedClock(datetime(2026, 10, 13, 12, tzinfo=UTC)),
    )
    kitchen_http = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(runtime)))
    app = FastAPI()
    app.include_router(
        build_router(KitchenGateway(A2ASkillClient("http://kitchen/", kitchen_http)), dev_user)
    )
    h = {"X-User-Id": str(user)}
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gw"
        ) as gw:
            added = await runtime.service.apply(
                user,
                ops=OperationList(
                    adds=[
                        AddItem(
                            name="курица",
                            display_name="курица",
                            quantity=1,
                            unit=InputUnit.KG,
                            location=Location.FRIDGE,
                            category=Category.MEAT,
                            shelf_life_days=2,
                        )
                    ]
                ),
                refs={},
                source=Source.TEXT,
            )
            item_id = added.changes[0].after.pk
            listed = (await gw.get("/kitchen/inventory", headers=h)).json()
            assert [i["name"] for i in listed["items"]] == ["курица"]
            assert listed["items"][0]["added_by"] == {"user_id": str(user), "name": "Аня"}
            digest = await gw.get("/kitchen/digest", headers=h)
            assert digest.status_code == 200
            assert [i["id"] for i in digest.json()["soon"]] == [str(item_id)]
            assert (await gw.get("/kitchen/inventory?location=freezer", headers=h)).json() == {
                "items": []
            }
            acted = await gw.post(
                f"/kitchen/items/{item_id}/action", json={"action": "consumed"}, headers=h
            )
            assert acted.status_code == 200
            assert acted.json()["item"]["id"] == str(item_id)
            assert acted.json()["item"]["name"] == "курица"
            assert acted.json()["item"]["quantity"] == "0"
            assert (await gw.get("/kitchen/inventory", headers=h)).json() == {"items": []}
            gone = await gw.post(
                f"/kitchen/items/{item_id}/action", json={"action": "consumed"}, headers=h
            )
            assert (gone.status_code, gone.json()) == (409, {"detail": "item_gone"})
            undone = await gw.post(f"/kitchen/undo/{acted.json()['group_id']}", headers=h)
            assert undone.status_code == 200
            assert undone.json() == {"outcome": "done"}
            repeated = await gw.post(f"/kitchen/undo/{acted.json()['group_id']}", headers=h)
            assert (repeated.status_code, repeated.json()) == (409, {"detail": "already_undone"})
            assert [
                i["name"] for i in (await gw.get("/kitchen/inventory", headers=h)).json()["items"]
            ] == ["курица"]
            missing = await gw.post(f"/kitchen/undo/{uuid4()}", headers=h)
            assert (missing.status_code, missing.json()) == (404, {"detail": "undo_not_found"})
            changed = await gw.post(
                f"/kitchen/items/{item_id}/action",
                json={"action": "set_expiry", "expires_on": "2026-10-25"},
                headers=h,
            )
            assert changed.status_code == 200
            assert changed.json()["item"]["expires_on"] == "2026-10-25"
            conflict = await gw.post(f"/kitchen/undo/{added.group_id}", headers=h)
            assert (conflict.status_code, conflict.json()) == (409, {"detail": "undo_conflict"})
            invalid = await gw.post(
                f"/kitchen/items/{item_id}/action",
                json={"action": "move"},
                headers=h,
            )
            assert (invalid.status_code, invalid.json()) == (422, {"detail": "invalid_params"})
            outsider = await gw.get("/kitchen/inventory", headers={"X-User-Id": str(uuid4())})
            assert (outsider.status_code, outsider.json()) == (404, {"detail": "no_household"})
            assert llm.calls == []
    finally:
        await kitchen_http.aclose()
        await runtime.engine.dispose()
