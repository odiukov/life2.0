from datetime import UTC, datetime
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
from sleep.application.log_sleep import LogSleep

NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)


def setup(locale: str = "ru"):  # type: ignore[no-untyped-def]
    logs, users, llm = InMemoryHealthLogs(), InMemoryUserSettings(), FakeLLM()
    user = uuid4()
    users.seed(user, timezone="Europe/Lisbon", locale=locale)
    handler = LogSleep(
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
        text="спал с 23:30 до 7, нормально",
        user_id=user,
        skill_id="log_sleep",
        for_date=None,
        is_peer_call=False,
    )
    return handler, llm, logs, request


async def test_stores_a_chat_session_with_garmin_keys_and_confirms() -> None:
    handler, llm, logs, request = setup()
    llm.queue_structured({"bed_time": "23:30", "wake_time": "07:00", "quality": 3})
    result = await handler(request, ())
    [row] = logs.rows[request.user_id]
    assert (row.type, row.agent, row.source) == ("sleep_session", "sleep", "chat")
    assert row.data["duration_seconds"] == 27000
    assert row.data["quality"] == 3
    assert result.output == "Записал сон: 23:30–07:00, 7,5 часа. Качество 3/5."
    assert result.log_entry == request.text
    assert result.log_recorded_at == row.recorded_at


async def test_whole_hours_in_english() -> None:
    handler, llm, _, request = setup("en")
    llm.queue_structured({"duration_minutes": 420})
    assert (await handler(request, ())).output == "Logged sleep: 03:00–10:00, 7 hours."


async def test_not_understood_stores_nothing() -> None:
    handler, llm, logs, request = setup()
    llm.queue_structured({"quality": 2})
    result = await handler(request, ())
    assert logs.rows == {}
    assert result.log_entry is None
    assert result.output.startswith("Не понял")


async def test_invalid_output_is_not_understood_and_unavailable_is_failed() -> None:
    handler, llm, logs, request = setup()
    llm.queue_structured(LLMInvalidOutput("{}", "bad"))
    assert (await handler(request, ())).output.startswith("Не понял")
    llm.queue_structured(LLMUnavailable("down"))
    failed = await handler(request, ())
    assert failed.failed
    assert failed.output.startswith("Сейчас не могу ответить")
    assert logs.rows == {}
