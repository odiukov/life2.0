from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from recovery.application.data import RecoveryData, window_days
from shared.a2a.request import SkillRequest
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.users import UserSettings
from shared.testing.fakes import InMemoryHealthLogs, InMemoryUnitOfWorkFactory

NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)


async def load(logs: InMemoryHealthLogs, user, mode: str = "get_readiness"):  # type: ignore[no-untyped-def]
    uow = InMemoryUnitOfWorkFactory({HealthLogRepository: logs})
    request = SkillRequest(
        task_id="t",
        context_id="c",
        text="как восстановление?",
        user_id=user,
        skill_id=mode,
        for_date=None,
        is_peer_call=False,
    )
    async with uow.for_user(user) as tx:
        return await RecoveryData(mode).load(
            tx, request, UserSettings(ZoneInfo("Europe/Lisbon"), None), NOW
        )


def test_windows() -> None:
    assert (
        window_days("analyze_recovery_trend"),
        window_days("get_readiness"),
        window_days("get_recommendations"),
    ) == (14, 8, 8)


async def test_no_data_overrides_the_tail() -> None:
    loaded = await load(InMemoryHealthLogs(), uuid4())
    assert loaded.tail_override is not None
    assert "readiness unknown" in loaded.tail_override
    assert loaded.sections[0].body == "No recovery data available yet."


async def test_snapshot_and_history_with_bucket() -> None:
    logs, user = InMemoryHealthLogs(), uuid4()
    for i in range(8):
        day = NOW - timedelta(days=i)
        logs.seed(
            user,
            HealthLogRow(
                "daily_stats",
                day.replace(hour=12),
                {"resting_hr": 50 if i == 0 else 56, "stress_avg": 30},
                "garmin",
                "sleep",
            ),
        )
        logs.seed(
            user,
            HealthLogRow(
                "hrv_status",
                day.replace(hour=6),
                {"hrv_rmssd": 60 if i == 0 else 48},
                "garmin",
                "sleep",
            ),
        )
        logs.seed(
            user,
            HealthLogRow(
                "sleep_session",
                day.replace(hour=0) - timedelta(hours=1),
                {"duration_seconds": 28800 if i == 0 else 25200, "awake_seconds": 600},
                "garmin",
                "sleep",
            ),
        )
    loaded = await load(logs, user)
    snapshot, history = loaded.sections
    assert snapshot.title == "Snapshot"
    assert snapshot.body.startswith("Bucket: recovered\nLatest (2026-10-13): HRV=60")
    assert history.title == "Last 7 days"
    assert len(history.body.splitlines()) == 7
    assert "RHR=50, stress=30, body_battery=" in snapshot.body
    assert history.body.splitlines()[0].startswith("2026-10-13: HRV=60, RHR=50, stress=30")
    assert loaded.tail_override is None
