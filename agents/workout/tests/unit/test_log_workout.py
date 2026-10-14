from datetime import UTC, datetime, timedelta
from uuid import uuid4

from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.config import find_locales_dir
from shared.ports.health_logs import HealthLogRepository
from shared.ports.llm import LLMInvalidOutput, LLMUnavailable
from shared.ports.users import UserSettingsRepository
from shared.testing.fakes import (
    FakeLLM,
    FixedClock,
    InMemoryHealthLogs,
    InMemoryUnitOfWorkFactory,
    InMemoryUserSettings,
    InMemoryVectorMemory,
)
from workout.application.log_workout import LogWorkout

NOW = datetime(2026, 10, 13, 17, 0, tzinfo=UTC)


def setup(locale: str = "ru"):  # type: ignore[no-untyped-def]
    logs, users, llm = InMemoryHealthLogs(), InMemoryUserSettings(), FakeLLM()
    user = uuid4()
    users.seed(user, timezone="Europe/Lisbon", locale=locale)
    handler = LogWorkout(
        llm=llm,
        uow=InMemoryUnitOfWorkFactory({HealthLogRepository: logs, UserSettingsRepository: users}),
        clock=FixedClock(NOW),
        translator=JsonTranslator.from_dir(find_locales_dir()),
        memory=InMemoryVectorMemory(),
        default_locale="ru",
    )
    request = SkillRequest(
        task_id="t",
        context_id="c",
        text="пробежал 5 км за 28 минут",
        user_id=user,
        skill_id="log_workout",
        for_date=None,
        is_peer_call=False,
    )
    return handler, llm, logs, request


async def test_stores_an_activity_row_with_garmin_keys() -> None:
    handler, llm, logs, request = setup()
    llm.queue_structured(
        {"activity_type": "running", "duration_minutes": 28, "distance_km": 5, "effort": 7}
    )
    result = await handler(request, ())
    [row] = logs.rows[request.user_id]
    assert (row.type, row.agent, row.source, row.recorded_at) == (
        "activity",
        "workout",
        "chat",
        NOW - timedelta(minutes=28),
    )
    assert row.data == {
        "activity_type": "running",
        "name": "running",
        "duration_seconds": 1680,
        "distance_meters": 5000,
        "effort": 7,
    }
    assert result.output == "Записал тренировку: бег, 28 мин, 5 км."
    assert result.log_entry == request.text


async def test_invalid_and_unavailable() -> None:
    handler, llm, logs, request = setup()
    llm.queue_structured(LLMInvalidOutput("{}", "bad"))
    assert (await handler(request, ())).output.startswith("Не понял")
    llm.queue_structured(LLMUnavailable("down"))
    assert (await handler(request, ())).failed
    assert logs.rows == {}


async def test_non_workout_is_not_stored() -> None:
    handler, llm, logs, request = setup()
    llm.queue_structured({"activity_type": "other", "duration_minutes": 1, "name": "none"})
    result = await handler(request, ())
    assert result.output.startswith("Не понял")
    assert result.log_entry is None
    assert logs.rows == {}


async def test_stated_future_start_is_yesterday_and_english_reply() -> None:
    handler, llm, logs, request = setup("en")
    llm.queue_structured(
        {
            "activity_type": "walking",
            "duration_minutes": 30,
            "started_at": "19:00",
            "distance_km": 2.5,
        }
    )
    result = await handler(request, ())
    [row] = logs.rows[request.user_id]
    assert row.recorded_at == datetime(2026, 10, 12, 18, tzinfo=UTC)
    assert result.log_recorded_at == row.recorded_at
    assert result.output == "Logged workout: walking, 30 min, 2.5 km."
