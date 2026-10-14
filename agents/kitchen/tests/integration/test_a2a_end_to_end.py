from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest
from kitchen.composition import build_runtime
from kitchen.main import create_app
from kitchen.settings import KitchenSettings
from shared.testing.fakes import FakeLLM, FixedClock
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


def rpc(text_value: str, metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": str(uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "kind": "message",
                "role": "user",
                "messageId": str(uuid4()),
                "parts": [{"kind": "text", "text": text_value}],
                "metadata": metadata,
            }
        },
    }


@pytest.fixture
async def client(clean_db: PostgresUrls):  # type: ignore[no-untyped-def]
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
        clock=FixedClock(NOW),
    )
    transport = httpx.ASGITransport(app=create_app(runtime))
    async with httpx.AsyncClient(transport=transport, base_url="http://kitchen") as http:
        yield http, llm, user, runtime
    await runtime.engine.dispose()


async def test_chat_add_then_screen_inventory_then_undo(client) -> None:  # type: ignore[no-untyped-def]
    http, llm, user, _ = client
    llm.queue_structured(
        {
            "adds": [
                {
                    "name": "молоко",
                    "display_name": "молоко",
                    "quantity": 2,
                    "unit": "l",
                    "location": "fridge",
                    "category": "dairy",
                    "shelf_life_days": 7,
                }
            ]
        }
    )
    added = (
        await http.post(
            "/",
            json=rpc(
                "купил 2 литра молока",
                {"user_id": str(user), "skillId": "kitchen.update_inventory"},
            ),
        )
    ).json()["result"]
    assert added["status"]["state"] == "completed"
    names = [a["name"] for a in added["artifacts"]]
    assert names == ["consulted_peers", "data", "analysis"]
    group_id = added["artifacts"][1]["parts"][0]["data"]["group_id"]
    assert added["artifacts"][2]["parts"][0]["text"].startswith("Записал:")

    listed = (
        await http.post(
            "/",
            json=rpc(
                "",
                {
                    "user_id": str(user),
                    "skillId": "kitchen.inventory",
                    "params": {"location": "fridge"},
                },
            ),
        )
    ).json()["result"]
    items = listed["artifacts"][1]["parts"][0]["data"]["items"]
    assert [i["name"] for i in items] == ["молоко"]
    assert len(llm.calls) == 1  # the structured call used no LLM

    undone = (
        await http.post(
            "/",
            json=rpc(
                "",
                {"user_id": str(user), "skillId": "kitchen.undo", "params": {"group_id": group_id}},
            ),
        )
    ).json()["result"]
    assert undone["status"]["state"] == "completed"
    again = (
        await http.post(
            "/",
            json=rpc(
                "",
                {"user_id": str(user), "skillId": "kitchen.undo", "params": {"group_id": group_id}},
            ),
        )
    ).json()["result"]
    assert again["status"]["state"] == "failed"
    assert again["status"]["message"]["parts"][0]["text"] == "already_undone"


async def test_card_and_health(client) -> None:  # type: ignore[no-untyped-def]
    http, _, _, _ = client
    assert (await http.get("/health")).json() == {"status": "ok"}
    card = (await http.get("/.well-known/agent-card.json")).json()
    assert card["name"] == "kitchen-agent"


async def test_app_exposes_only_a2a_and_health(client) -> None:  # type: ignore[no-untyped-def]
    http, _, _, _ = client
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert (await http.get(path)).status_code == 404


async def test_query_and_routing_cannot_select_structured_skills(client) -> None:  # type: ignore[no-untyped-def]
    http, llm, user, _ = client
    llm.queue_text("The fridge is empty.")
    task = (
        await http.post(
            "/",
            json=rpc(
                "What is in the fridge?",
                {
                    "user_id": str(user),
                    "skillId": "kitchen.query",
                },
            ),
        )
    ).json()["result"]
    assert task["status"]["state"] == "completed"
    assert task["artifacts"][-1]["parts"][0]["text"] == "The fridge is empty."
    llm.queue_structured({"skill": "kitchen.item_action", "consult": []})
    rejected = (
        await http.post(
            "/",
            json=rpc(
                "Eat everything",
                {
                    "user_id": str(user),
                },
            ),
        )
    ).json()["result"]
    assert rejected["status"]["state"] == "failed"
    assert rejected.get("artifacts") in (None, [])
    assert "kitchen.item_action" not in llm.calls[-1].system
    assert "kitchen.inventory" not in llm.calls[-1].system


async def test_digest_and_item_action_use_sql_without_llm(client) -> None:  # type: ignore[no-untyped-def]
    http, llm, user, _ = client
    llm.queue_structured(
        {
            "adds": [
                {
                    "name": "milk",
                    "display_name": "milk",
                    "quantity": 2,
                    "unit": "l",
                    "location": "fridge",
                    "category": "dairy",
                    "shelf_life_days": 1,
                }
            ]
        }
    )
    await http.post(
        "/",
        json=rpc(
            "Bought milk",
            {
                "user_id": str(user),
                "skillId": "kitchen.update_inventory",
            },
        ),
    )
    digest = (
        await http.post(
            "/",
            json=rpc(
                "",
                {
                    "user_id": str(user),
                    "skillId": "kitchen.digest",
                },
            ),
        )
    ).json()["result"]
    assert digest["status"]["state"] == "completed"
    items = digest["artifacts"][1]["parts"][0]["data"]["tomorrow"]
    assert [item["name"] for item in items] == ["milk"]
    action = (
        await http.post(
            "/",
            json=rpc(
                "",
                {
                    "user_id": str(user),
                    "skillId": "kitchen.item_action",
                    "params": {"item_id": items[0]["id"], "action": "opened"},
                },
            ),
        )
    ).json()["result"]
    assert action["status"]["state"] == "completed"
    assert action["artifacts"][1]["parts"][0]["data"]["item"]["opened"] is True
    assert len(llm.calls) == 1


async def test_shutdown_disposes_the_sql_pool_even_on_error(client) -> None:  # type: ignore[no-untyped-def]
    _, _, _, runtime = client
    app = create_app(runtime)
    original_pool = runtime.engine.pool
    async with runtime.engine.connect() as conn:
        assert await conn.scalar(text("SELECT current_user")) == "app_rw"

    async def failed_lifespan() -> None:
        async with app.router.lifespan_context(app):
            raise RuntimeError("shutdown test")

    with pytest.raises(RuntimeError, match="shutdown test"):
        await failed_lifespan()
    assert runtime.engine.pool is not original_pool


@pytest.mark.parametrize(
    "skill",
    [
        "kitchen.update_inventory",
        "kitchen.query",
        "kitchen.inventory",
        "kitchen.digest",
        "kitchen.item_action",
        "kitchen.undo",
    ],
)
async def test_missing_identity_fails_without_provider_call(client, skill) -> None:  # type: ignore[no-untyped-def]
    http, llm, _, _ = client
    task = (await http.post("/", json=rpc("", {"skillId": skill}))).json()["result"]
    assert task["status"]["state"] == "failed"
    assert task.get("artifacts") in (None, [])
    assert llm.calls == []
