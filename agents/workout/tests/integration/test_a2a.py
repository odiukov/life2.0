from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest
from shared.testing.fakes import FakeLLM, FakePeerClient, FixedClock, InMemoryVectorMemory
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from workout.composition import build_runtime
from workout.main import create_app
from workout.settings import WorkoutSettings

pytestmark = pytest.mark.integration
NOW = datetime(2026, 10, 13, 17, 0, tzinfo=UTC)


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


async def test_logged_workout_shows_up_in_the_next_analysis(clean_db: PostgresUrls) -> None:
    me = uuid4()
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        await conn.execute(
            text("INSERT INTO users (id, name, timezone) VALUES (:a, 'a', 'Europe/Lisbon')"),
            {"a": me},
        )
    await admin.dispose()
    llm = FakeLLM()
    llm.queue_structured({"activity_type": "running", "duration_minutes": 28, "distance_km": 5})
    llm.queue_text("Хорошая неделя.")
    runtime = build_runtime(
        WorkoutSettings.model_validate({"database": {"dsn": clean_db.rw}}),
        llm=llm,
        peers=FakePeerClient(),
        memory=InMemoryVectorMemory(),
        clock=FixedClock(NOW),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runtime)), base_url="http://w"
    ) as http:
        logged = (
            await http.post(
                "/", json=rpc("пробежал 5 км", {"user_id": str(me), "skillId": "log_workout"})
            )
        ).json()["result"]
        analysed = (
            await http.post(
                "/", json=rpc("как неделя?", {"user_id": str(me), "skillId": "analyze_workout"})
            )
        ).json()["result"]
    assert [a["name"] for a in logged["artifacts"]] == ["log_entry", "consulted_peers", "analysis"]
    assert analysed["status"]["state"] == "completed"
    assert "| chat | running | 28 min | 5.0 km" in llm.calls[-1].user
    await runtime.engine.dispose()
