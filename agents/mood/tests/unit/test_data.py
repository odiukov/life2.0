from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from mood.application.data import MoodData
from shared.a2a.request import SkillRequest
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.users import UserSettings
from shared.testing.fakes import InMemoryHealthLogs, InMemoryUnitOfWorkFactory

NOW = datetime(2026, 10, 13, 18, 0, tzinfo=UTC)


async def load(logs: InMemoryHealthLogs, user, mode: str):  # type: ignore[no-untyped-def]
    uow = InMemoryUnitOfWorkFactory({HealthLogRepository: logs})
    request = SkillRequest(
        task_id="t",
        context_id="c",
        text="как настроение",
        user_id=user,
        skill_id=mode,
        for_date=None,
        is_peer_call=False,
    )
    async with uow.for_user(user) as tx:
        return await MoodData(mode).load(tx, request, UserSettings(ZoneInfo("UTC"), None), NOW)


@pytest.mark.parametrize("mode", ["analyze_mood", "get_mood_recommendations"])
async def test_empty_history_overrides_the_tail(mode: str) -> None:
    loaded = await load(InMemoryHealthLogs(), uuid4(), mode)
    assert loaded.sections[0].body == "No mood entries yet."
    assert loaded.tail_override is not None
    assert "log a few" in loaded.tail_override


async def test_latest_thirty_entries() -> None:
    logs, user = InMemoryHealthLogs(), uuid4()
    for i in range(35):
        logs.seed(
            user,
            HealthLogRow("mood", NOW - timedelta(hours=i), {"mood_score": 5}, "manual", "mood"),
        )
    loaded = await load(logs, user, "analyze_mood")
    assert loaded.sections[0].title == "Recent mood entries (latest 30)"
    assert len(loaded.sections[0].body.splitlines()) == 30
    assert loaded.tail_override is None
