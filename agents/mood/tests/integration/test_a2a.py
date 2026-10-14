from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest
from mood.composition import build_runtime
from mood.main import create_app
from mood.settings import MoodSettings
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


async def test_logged_mood_has_the_dashboard_shape(clean_db: PostgresUrls) -> None:
    me = uuid4()
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        await conn.execute(
            text("INSERT INTO users (id, name, timezone) VALUES (:a, 'a', 'Europe/Lisbon')"),
            {"a": me},
        )
    llm = FakeLLM()
    llm.queue_structured({"mood_score": 7, "tags": ["calm"], "summary": "calm"})
    peers = FakePeerClient({"sleep": "two short nights"})
    runtime = build_runtime(
        MoodSettings.model_validate({"database": {"dsn": clean_db.rw}}),
        llm=llm,
        peers=peers,
        memory=InMemoryVectorMemory(),
        clock=FixedClock(datetime.now(UTC)),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runtime)), base_url="http://m"
    ) as http:
        task = (
            await http.post(
                "/", json=rpc("спокойно, 7", {"user_id": str(me), "skillId": "log_mood"})
            )
        ).json()["result"]
        llm.queue_text("mood trend", "peer mood trend")
        analysis = (
            await http.post(
                "/", json=rpc("trend?", {"user_id": str(me), "skillId": "analyze_mood"})
            )
        ).json()["result"]
        assert analysis["status"]["state"] == "completed"
        assert peers.calls[0]["wanted"] == {"sleep": "analyze_sleep"}
        assert "mood_score=7" in llm.calls[-1].user
        peer_task = (
            await http.post(
                "/",
                json=rpc(
                    "trend?", {"user_id": str(me), "skillId": "analyze_mood", "is_peer_call": True}
                ),
            )
        ).json()["result"]
        assert peer_task["status"]["state"] == "completed"
        assert len(peers.calls) == 1
    assert [a["name"] for a in task["artifacts"]] == ["log_entry", "consulted_peers", "analysis"]
    async with admin.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT agent, source, data FROM health_logs WHERE user_id = :u AND type = 'mood'"
                ),
                {"u": me},
            )
        ).one()
    assert (row.agent, row.source, row.data["mood_score"], row.data["source_skill"]) == (
        "mood",
        "manual",
        7,
        "log_mood",
    )
    await admin.dispose()
    await runtime.engine.dispose()
