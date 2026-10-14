from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest
from body.composition import build_runtime
from body.main import create_app
from body.settings import BodySettings
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


async def test_get_latest_reads_this_users_rows_only(clean_db: PostgresUrls) -> None:
    me, other = uuid4(), uuid4()
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, name, timezone) VALUES (:a, 'a', 'Europe/Lisbon'), (:b, 'b', 'UTC')"
            ),
            {"a": me, "b": other},
        )
        for uid, weight in ((me, 82.5), (other, 60.0)):
            await conn.execute(
                text(
                    "INSERT INTO health_logs (user_id, agent, type, source, data) VALUES (:u, 'body', 'body_composition', 'vihealth', CAST(:d AS jsonb))"
                ),
                {"u": uid, "d": f'{{"weight_kg": {weight}}}'},
            )
    await admin.dispose()
    llm = FakeLLM()
    llm.queue_text("Вес 82.5 кг.")
    runtime = build_runtime(
        BodySettings.model_validate({"database": {"dsn": clean_db.rw}}),
        llm=llm,
        peers=FakePeerClient(),
        memory=InMemoryVectorMemory(),
        clock=FixedClock(datetime.now(UTC)),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runtime)), base_url="http://body"
    ) as http:
        task = (
            await http.post(
                "/", json=rpc("сколько я вешу", {"user_id": str(me), "skillId": "get_latest_body"})
            )
        ).json()["result"]
        assert task["status"]["state"] == "completed"
        assert [a["name"] for a in task["artifacts"]] == ["consulted_peers", "analysis"]
        assert "weight=82.5kg" in llm.calls[0].user
        assert "60.0" not in llm.calls[0].user
        assert (await http.get("/.well-known/agent-card.json")).json()["name"] == "body-agent"
    await runtime.engine.dispose()
