from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest
from medication.composition import build_runtime
from medication.main import create_app
from medication.settings import MedicationSettings
from shared.testing.fakes import FakeLLM, FakePeerClient, FixedClock, InMemoryVectorMemory
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


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


def reply(task: dict[str, Any]) -> str:
    return str(task["artifacts"][-1]["parts"][0]["text"])


async def test_define_log_list_analyze(clean_db: PostgresUrls) -> None:
    me = uuid4()
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        await conn.execute(
            text("INSERT INTO users (id, name, timezone) VALUES (:a, 'a', 'Europe/Lisbon')"),
            {"a": me},
        )
    await admin.dispose()
    llm = FakeLLM()
    llm.queue_structured(
        {"name": "vitamin-d", "dose": "2000 IU", "schedule": "every morning"}, {"name": "vitamin-d"}
    )
    llm.queue_text("Пропусков нет.")
    runtime = build_runtime(
        MedicationSettings.model_validate({"database": {"dsn": clean_db.rw}}),
        llm=llm,
        peers=FakePeerClient(),
        memory=InMemoryVectorMemory(),
        clock=FixedClock(datetime.now(UTC)),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runtime)), base_url="http://m"
    ) as http:

        async def call(text_value: str, skill: str) -> dict[str, Any]:
            return (
                await http.post("/", json=rpc(text_value, {"user_id": str(me), "skillId": skill}))
            ).json()["result"]

        assert reply(await call("витамин D 2000 МЕ каждое утро", "define_medication")).startswith(
            "Отслеживаю «vitamin-d»"
        )
        logged = await call("принял витамин д", "log_medication")
        assert [a["name"] for a in logged["artifacts"]] == [
            "log_entry",
            "consulted_peers",
            "analysis",
        ]
        assert reply(await call("", "list_active")) == "• vitamin-d 2000 IU · every morning"
        assert reply(await call("как с приёмом?", "analyze_adherence")) == "Пропусков нет."
        assert "taken 1×" in llm.calls[-1].user
        archived = await call("vitamin-d", "archive_medication")
        assert reply(archived) == "Убрал «vitamin-d» из списка."
        assert [a["name"] for a in archived["artifacts"]] == [
            "log_entry",
            "consulted_peers",
            "analysis",
        ]
        assert reply(await call("", "list_active")) == "Активных лекарств нет."
        assert (
            reply(await call("как с приёмом?", "analyze_adherence"))
            == "Нет активных лекарств — анализировать нечего."
        )
    admin = create_async_engine(clean_db.admin)
    async with admin.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT type, agent, source, data FROM health_logs WHERE user_id = :u"),
                {"u": me},
            )
        ).one()
        assert (row.type, row.agent, row.source) == ("medication_taken", "medication", "manual")
        assert row.data == {
            "name": "vitamin-d",
            "medication_id": row.data["medication_id"],
            "dose_at_time": "2000 IU",
            "note": None,
            "raw_text": "принял витамин д",
            "source_skill": "log_medication",
        }
    await admin.dispose()
    await runtime.engine.dispose()
