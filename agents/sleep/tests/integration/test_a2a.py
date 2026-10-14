from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest
from recovery.domain.daily import RECOVERY_TYPES, assemble_days
from shared.adapters.db.engine import create_engine
from shared.adapters.db.health_logs import SqlHealthLogs
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.config import DatabaseSettings
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.testing.fakes import FakeLLM, FakePeerClient, FixedClock, InMemoryVectorMemory
from shared.testing.pytest_plugin import PostgresUrls
from sleep.composition import build_runtime
from sleep.main import create_app
from sleep.settings import SleepSettings
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


async def test_chat_sleep_is_stored_and_recovery_sees_it(clean_db: PostgresUrls) -> None:
    me = uuid4()
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        await conn.execute(
            text("INSERT INTO users (id, name, timezone) VALUES (:a, 'a', 'Europe/Lisbon')"),
            {"a": me},
        )
    await admin.dispose()
    llm = FakeLLM()
    llm.queue_structured({"bed_time": "23:30", "wake_time": "07:00"})
    runtime = build_runtime(
        SleepSettings.model_validate({"database": {"dsn": clean_db.rw}}),
        llm=llm,
        peers=FakePeerClient(),
        memory=InMemoryVectorMemory(),
        clock=FixedClock(NOW),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runtime)), base_url="http://s"
    ) as http:
        task = (
            await http.post(
                "/", json=rpc("спал с 23:30 до 7", {"user_id": str(me), "skillId": "log_sleep"})
            )
        ).json()["result"]
    assert task["status"]["state"] == "completed"
    assert [a["name"] for a in task["artifacts"]] == ["log_entry", "consulted_peers", "analysis"]
    engine = create_engine(DatabaseSettings.model_validate({"dsn": clean_db.rw}))
    uow = SqlUnitOfWorkFactory(engine, {HealthLogRepository: SqlHealthLogs})
    async with uow.for_user(me) as tx:
        rows = await tx.repo(HealthLogRepository).recent(
            me, types=list(RECOVERY_TYPES), since=NOW - timedelta(days=2)
        )
    assert [(r.source, r.data["duration_seconds"]) for r in rows] == [("chat", 27000)]
    assert (
        assemble_days(rows, ZoneInfo("Europe/Lisbon"))[date(2026, 10, 12)].sleep_duration_h == 7.5
    )
    # A device row at the exact same instant must coexist (source is in the dedup key).
    async with uow.for_user(me) as tx:
        await tx.repo(HealthLogRepository).add(
            me,
            HealthLogRow(
                type="sleep_session",
                recorded_at=rows[0].recorded_at,
                data={"duration_seconds": 25200},
                source="garmin",
                agent="sleep",
            ),
        )
        both = await tx.repo(HealthLogRepository).recent(me, types=["sleep_session"])
    assert {r.source for r in both} == {"chat", "garmin"}
    assert len(both) == 2
    assert both[0].recorded_at == both[1].recorded_at
    assert assemble_days(both, ZoneInfo("Europe/Lisbon"))[date(2026, 10, 12)].sleep_duration_h == 7
    await engine.dispose()
    await runtime.engine.dispose()
