from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from nutrition.composition import build_runtime
from nutrition.main import create_app
from nutrition.settings import NutritionSettings
from nutrition.testing import FakeSync
from shared.testing.fakes import FakeLLM, FakePeerClient, FixedClock, InMemoryVectorMemory
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)


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
async def client_and_llm(clean_db: PostgresUrls):
    user = uuid4()
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        await conn.execute(
            text("INSERT INTO users (id, name, timezone) VALUES (:id, 'me', 'Europe/Lisbon')"),
            {"id": user},
        )
    await admin.dispose()
    llm = FakeLLM()
    settings = NutritionSettings.model_validate({"database": {"dsn": clean_db.rw}})
    peers = FakePeerClient()
    memory = InMemoryVectorMemory()
    runtime = build_runtime(
        settings,
        llm=llm,
        memory=memory,
        peers=peers,
        sync=FakeSync(),
        clock=FixedClock(NOW),
    )
    transport = httpx.ASGITransport(app=create_app(runtime))
    async with httpx.AsyncClient(transport=transport, base_url="http://nutrition") as client:
        yield client, llm, user, peers, runtime, memory
    await runtime.engine.dispose()


async def test_card_is_served(client_and_llm) -> None:
    client, _, _, _, _, _ = client_and_llm
    card = (await client.get("/.well-known/agent-card.json")).json()
    assert card["name"] == "nutrition-agent"
    assert {s["id"] for s in card["skills"]} >= {"log_meal", "analyze_nutrition"}


async def test_logged_meal_is_counted_in_todays_analysis(client_and_llm) -> None:
    client, llm, user, _, _, _ = client_and_llm
    llm.queue_structured(
        {
            "items": [
                {
                    "name": "омлет",
                    "amount_g": 180,
                    "kcal": 300,
                    "protein_g": 20,
                    "carbs_g": 2,
                    "fat_g": 22,
                },
                {
                    "name": "тост",
                    "amount_g": 30,
                    "kcal": 120,
                    "protein_g": 7,
                    "carbs_g": 16,
                    "fat_g": 4,
                },
            ],
            "confidence": "high",
        }
    )
    logged = (
        await client.post(
            "/",
            json=rpc("съел омлет из 3 яиц и тост", {"user_id": str(user), "skillId": "log_meal"}),
        )
    ).json()
    task = logged["result"]
    assert task["status"]["state"] == "completed"
    assert [a["name"] for a in task["artifacts"]] == ["log_entry", "consulted_peers", "analysis"]
    assert task["artifacts"][2]["parts"][0]["text"].startswith(
        "Записал: омлет (180 г), тост (30 г) — 420 ккал"
    )

    llm.queue_text("Сегодня 420 ккал из ~2700.")
    analysed = (
        await client.post(
            "/",
            json=rpc(
                "как сегодня с питанием?", {"user_id": str(user), "skillId": "analyze_nutrition"}
            ),
        )
    ).json()
    assert analysed["result"]["artifacts"][-1]["parts"][0]["text"] == "Сегодня 420 ккал из ~2700."
    assert "Eaten: 420 kcal" in llm.calls[-1].user


async def test_missing_user_fails_the_task(client_and_llm) -> None:
    client, _, _, _, _, _ = client_and_llm
    reply = (await client.post("/", json=rpc("съел суп", {"skillId": "log_meal"}))).json()
    assert reply["result"]["status"]["state"] == "failed"


@pytest.mark.parametrize(
    ("skill", "names"),
    [
        ("log_meal", ["log_entry", "consulted_peers", "analysis"]),
        ("analyze_nutrition", ["consulted_peers", "analysis"]),
        ("get_nutrition_recommendations", ["consulted_peers", "analysis"]),
        ("set_body_profile", ["consulted_peers", "analysis"]),
    ],
)
async def test_every_real_handler_completes_with_legacy_artifact_order(
    client_and_llm, skill, names
) -> None:
    client, llm, user, _, runtime, _ = client_and_llm
    if skill == "log_meal":
        llm.queue_structured(
            {
                "items": [
                    {
                        "name": "soup",
                        "amount_g": 200,
                        "kcal": 150,
                        "protein_g": 8,
                        "carbs_g": 10,
                        "fat_g": 9,
                    }
                ],
                "confidence": "high",
            }
        )
    elif skill == "set_body_profile":
        llm.queue_structured({"height_cm": 180, "age": 30, "sex": "male"})
    else:
        llm.queue_text("fixture output")
    response = await client.post(
        "/", json=rpc("fixture input", {"user_id": str(user), "skillId": skill})
    )
    assert response.status_code == 200
    task = response.json()["result"]
    assert task["status"]["state"] == "completed"
    assert [a["name"] for a in task["artifacts"]] == names
    for artifact in task["artifacts"]:
        expected_kind = "text" if artifact["name"] == "analysis" else "data"
        assert artifact["parts"][0]["kind"] == expected_kind
    async with runtime.engine.connect() as conn:
        assert await conn.scalar(text("SELECT current_user")) == "app_rw"
        row = (
            await conn.execute(
                text(
                    "SELECT agent, skill_id, state, input, output, artifacts FROM tasks WHERE task_id = :id"
                ),
                {"id": UUID(task["id"])},
            )
        ).one()
    assert (row.agent, row.state) == ("nutrition", "completed")
    assert row.output == task["artifacts"][-1]["parts"][0]["text"]
    assert [artifact["name"] for artifact in row.artifacts] == names
    # Preserve Task9's legacy upsert: the SDK creates the initial row before
    # the executor records it, and initial skill/input fields stay immutable.
    assert row.skill_id is None
    assert row.input == {}


@pytest.mark.parametrize("is_peer", [False, True])
async def test_composed_analysis_preserves_depth_one_and_user_identity(client_and_llm, is_peer):
    client, llm, user, peers, _, _ = client_and_llm
    peers.answers = {"workout": "training context"}
    llm.queue_text("fixture output")
    task = (
        await client.post(
            "/",
            json=rpc(
                "analyze",
                {
                    "user_id": str(user),
                    "skillId": "analyze_nutrition",
                    "focus_sources": ["workout"],
                    "is_peer_call": is_peer,
                },
            ),
        )
    ).json()["result"]
    assert task["status"]["state"] == "completed"
    consulted = task["artifacts"][0]["parts"][0]["data"]["peers"]
    if is_peer:
        assert peers.calls == []
        assert consulted == []
    else:
        assert peers.calls[0]["user_id"] == user
        assert peers.calls[0]["wanted"] == {"workout": "analyze_workout"}
        assert consulted == ["workout"]


@pytest.mark.parametrize("invalid_user", [None, "not-a-uuid", 123])
async def test_invalid_user_fails_without_calling_any_handler(client_and_llm, invalid_user):
    client, llm, _, peers, _, _ = client_and_llm
    reply = (
        await client.post(
            "/",
            json=rpc(
                "soup",
                {
                    "skillId": "log_meal",
                    "user_id": invalid_user,
                },
            ),
        )
    ).json()["result"]
    assert reply["status"]["state"] == "failed"
    assert reply.get("artifacts") in (None, [])
    assert llm.calls == []
    assert peers.calls == []


async def test_health_route_and_shutdown_dispose_the_runtime_engine(client_and_llm):
    client, _, _, _, runtime, _ = client_and_llm
    assert (await client.get("/health")).json() == {"status": "ok"}
    app = create_app(runtime)
    async with app.router.lifespan_context(app):
        pass
    assert runtime.engine.pool.checkedout() == 0


@pytest.mark.parametrize(
    "skill", ["log_meal", "analyze_nutrition", "get_nutrition_recommendations"]
)
async def test_real_provider_failure_is_failed_without_meal_memory_or_success_record(
    client_and_llm, skill, monkeypatch
) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from a2a.types import Task
    from shared.adapters import peers as peer_adapter
    from shared.adapters.i18n import JsonTranslator
    from shared.config import find_locales_dir
    from shared.ports.llm import LLMUnavailable

    client, llm, user, _, runtime, memory = client_and_llm
    failure = LLMUnavailable("provider exception contains private diagnostic")
    if skill == "log_meal":
        llm.queue_structured(failure)
    else:
        llm.queue_text(failure)
    reply = (
        await client.post(
            "/",
            json=rpc(
                "soup",
                {
                    "skillId": skill,
                    "user_id": str(user),
                    "is_peer_call": True,
                },
            ),
        )
    ).json()["result"]
    assert reply["status"]["state"] == "failed"
    friendly = JsonTranslator.from_dir(find_locales_dir()).t(
        "nutrition.errors.llm_unavailable", "ru"
    )
    assert reply["status"]["message"]["parts"][0]["text"] == friendly
    assert reply.get("artifacts") in (None, [])
    assert memory.items == []
    async with runtime.engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(user)})
        assert await conn.scalar(text("SELECT count(*) FROM health_logs")) == 0
        row = (
            await conn.execute(
                text("SELECT agent, state, output, artifacts FROM tasks WHERE task_id = :id"),
                {"id": UUID(reply["id"])},
            )
        ).one()
        assert (row.agent, row.state, row.output, row.artifacts) == (
            "nutrition",
            "failed",
            None,
            [],
        )
        assert await conn.scalar(text("SELECT count(*) FROM tasks WHERE state='completed'")) == 0

    async def send_message(message):
        yield Task.model_validate(reply), None

    monkeypatch.setattr(
        peer_adapter,
        "_get_client",
        AsyncMock(return_value=SimpleNamespace(send_message=send_message)),
    )
    assert (
        await peer_adapter.call_peer("http://nutrition", skill, user_id=str(user))
        == peer_adapter.LEGACY_UNAVAILABLE
    )


async def test_malformed_model_output_fails_but_valid_empty_extraction_completes(client_and_llm):
    from shared.ports.llm import LLMInvalidOutput

    client, llm, user, _, _, memory = client_and_llm
    llm.queue_structured(
        LLMInvalidOutput("private raw model answer", "schema mismatch"), {"items": []}
    )
    metadata = {"skillId": "log_meal", "user_id": str(user)}
    failed = (await client.post("/", json=rpc("soup", metadata))).json()["result"]
    assert failed["status"]["state"] == "failed"
    assert failed["status"]["message"]["parts"][0]["text"].startswith("Не понял")
    assert failed.get("artifacts") in (None, [])
    clarified = (await client.post("/", json=rpc("hello", metadata))).json()["result"]
    assert clarified["status"]["state"] == "completed"
    assert [a["name"] for a in clarified["artifacts"]] == ["consulted_peers", "analysis"]
    assert clarified["artifacts"][-1]["parts"][0]["text"].startswith("Не понял")
    assert memory.items == []
