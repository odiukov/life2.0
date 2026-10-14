from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest
from habits.composition import build_runtime
from habits.main import create_app
from habits.settings import HabitsSettings
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


async def test_define_check_streak_through_a2a(clean_db: PostgresUrls) -> None:
    me = uuid4()
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, name, timezone, preferences) VALUES (:a, 'a', 'Europe/Lisbon', '{\"locale\": \"en\"}'::jsonb)"
            ),
            {"a": me},
        )
    await admin.dispose()
    llm = FakeLLM()
    llm.queue_structured({"name": "meditation", "kind": "boolean", "cadence_type": "daily"})
    runtime = build_runtime(
        HabitsSettings.model_validate({"database": {"dsn": clean_db.rw}}),
        llm=llm,
        peers=FakePeerClient(),
        memory=InMemoryVectorMemory(),
        clock=FixedClock(datetime.now(UTC)),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runtime)), base_url="http://h"
    ) as http:
        defined = (
            await http.post(
                "/",
                json=rpc("медитация каждый день", {"user_id": str(me), "skillId": "define_habit"}),
            )
        ).json()["result"]
        checked = (
            await http.post(
                "/", json=rpc("meditation", {"user_id": str(me), "skillId": "log_habit_check"})
            )
        ).json()["result"]
        streak = (
            await http.post(
                "/", json=rpc("", {"user_id": str(me), "skillId": "get_streak_summary"})
            )
        ).json()["result"]
    assert defined["artifacts"][-1]["parts"][0]["text"] == "Tracking “meditation” (daily)."
    assert [a["name"] for a in checked["artifacts"]] == ["log_entry", "consulted_peers", "analysis"]
    assert streak["artifacts"][-1]["parts"][0]["text"] == "✅ meditation — 1 day"
    await runtime.engine.dispose()
