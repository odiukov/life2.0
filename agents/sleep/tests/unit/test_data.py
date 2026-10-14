from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from shared.a2a.request import SkillRequest
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.users import UserSettings
from shared.testing.fakes import InMemoryHealthLogs, InMemoryUnitOfWorkFactory
from sleep.application.data import SleepData

NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)


async def test_analysis_lists_both_sources() -> None:
    logs, user = InMemoryHealthLogs(), uuid4()
    logs.seed(
        user,
        HealthLogRow(
            "sleep_session",
            NOW - timedelta(hours=10),
            {"duration_seconds": 25200},
            "garmin",
            "sleep",
        ),
    )
    logs.seed(
        user,
        HealthLogRow(
            "sleep_session",
            NOW - timedelta(hours=9, minutes=50),
            {"duration_seconds": 27000},
            "chat",
            "sleep",
        ),
    )
    logs.seed(
        user,
        HealthLogRow(
            "hrv_status",
            NOW - timedelta(hours=3),
            {"hrv_rmssd": 48, "status": "BALANCED"},
            "garmin",
            "sleep",
        ),
    )
    logs.seed(user, HealthLogRow("daily_stats", NOW, {"resting_hr": 50}, "garmin", "sleep"))
    uow = InMemoryUnitOfWorkFactory({HealthLogRepository: logs})
    request = SkillRequest(
        task_id="t",
        context_id="c",
        text="как сплю",
        user_id=user,
        skill_id="analyze_sleep",
        for_date=None,
        is_peer_call=False,
    )
    async with uow.for_user(user) as tx:
        loaded = await SleepData().load(
            tx, request, UserSettings(ZoneInfo("Europe/Lisbon"), None), NOW
        )
    sessions, hrv = loaded.sections
    assert sessions.title == "Recent sleep sessions (last 10)"
    assert "| chat | 7.5h" in sessions.body
    assert "| garmin | 7.0h" in sessions.body
    assert hrv.title == "Overnight HRV (last 7)"
    assert "rmssd=48 | BALANCED" in hrv.body
    assert "resting_hr" not in sessions.body + hrv.body
