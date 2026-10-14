from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import pytest
from recovery.composition import build_runtime
from recovery.main import create_app
from recovery.settings import RecoverySettings
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


async def test_healthkit_only_user_gets_a_real_snapshot(clean_db: PostgresUrls) -> None:
    me, other = uuid4(), uuid4()
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, name, timezone) VALUES (:a, 'a', 'America/New_York'), (:b, 'b', 'UTC')"
            ),
            {"a": me, "b": other},
        )
        for i in range(8):
            day = (NOW - timedelta(days=i)).replace(hour=0, minute=0)
            await conn.execute(
                text(
                    "INSERT INTO health_logs (user_id, agent, type, source, recorded_at, data) VALUES (:u, 'system', 'daily_stats', 'Apple Watch', :t, CAST(:d AS jsonb))"
                ),
                {
                    "u": me,
                    "t": day,
                    "d": '{"restingHeartRate": 54, "heartRateVariabilitySDNN": 47.5}',
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO health_logs (user_id, agent, type, source, recorded_at, data) VALUES (:u, 'sleep', 'daily_stats', 'garmin', :t, CAST(:d AS jsonb))"
                ),
                {"u": other, "t": day.replace(hour=12), "d": '{"resting_hr": 99}'},
            )
    await admin.dispose()
    llm = FakeLLM()
    llm.queue_text("Готов.")
    runtime = build_runtime(
        RecoverySettings.model_validate({"database": {"dsn": clean_db.rw}}),
        llm=llm,
        peers=FakePeerClient(),
        memory=InMemoryVectorMemory(),
        clock=FixedClock(NOW),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runtime)), base_url="http://r"
    ) as http:
        task = (
            await http.post(
                "/", json=rpc("готов?", {"user_id": str(me), "skillId": "get_readiness"})
            )
        ).json()["result"]
    assert task["status"]["state"] == "completed"
    assert [a["name"] for a in task["artifacts"]] == ["consulted_peers", "analysis"]
    prompt = llm.calls[0].user
    assert "HRV=47.5" in prompt
    assert "RHR=54" in prompt
    assert "99" not in prompt
    assert "2026-10-13" in prompt  # the HealthKit day did not slide to the 12th in New York
    await runtime.engine.dispose()
