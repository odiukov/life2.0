from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from shared.a2a.request import SkillRequest
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.users import UserSettings
from shared.testing.fakes import InMemoryHealthLogs, InMemoryUnitOfWorkFactory
from workout.application.data import WorkoutData

NOW = datetime(2026, 10, 13, 17, 0, tzinfo=UTC)


async def test_activities_only_and_last_five_body_measurements() -> None:
    logs, user = InMemoryHealthLogs(), uuid4()
    for i in range(12):
        logs.seed(
            user,
            HealthLogRow(
                "activity",
                NOW - timedelta(days=i),
                {"activity_type": "running", "duration_seconds": 1800},
                "garmin",
                "workout",
            ),
        )
    for i in range(7):
        logs.seed(
            user,
            HealthLogRow(
                "body_composition",
                NOW - timedelta(days=i),
                {"weight_kg": 82 + i},
                "vihealth",
                "workout",
            ),
        )
    uow = InMemoryUnitOfWorkFactory({HealthLogRepository: logs})
    request = SkillRequest(
        task_id="t",
        context_id="c",
        text="как тренировки",
        user_id=user,
        skill_id="analyze_workout",
        for_date=None,
        is_peer_call=False,
    )
    async with uow.for_user(user) as tx:
        loaded = await WorkoutData().load(
            tx, request, UserSettings(ZoneInfo("Europe/Lisbon"), None), NOW
        )
    workouts, body = loaded.sections
    assert workouts.title == "Recent workouts (last 10)"
    assert len(workouts.body.splitlines()) == 10
    assert body.title == "Body composition (last 5 measurements)"
    assert len(body.body.splitlines()) == 5
