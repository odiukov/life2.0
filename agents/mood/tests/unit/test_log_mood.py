from datetime import UTC, datetime
from uuid import uuid4

from mood.application.log_mood import LogMood
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

NOW = datetime(2026, 10, 13, 18, 5, tzinfo=UTC)


def setup(params: dict[str, object] | None = None):  # type: ignore[no-untyped-def]
    logs, users, llm, memory = (
        InMemoryHealthLogs(),
        InMemoryUserSettings(),
        FakeLLM(),
        InMemoryVectorMemory(),
    )
    user = uuid4()
    users.seed(user, timezone="Europe/Lisbon", locale="ru")
    handler = LogMood(
        llm=llm,
        uow=InMemoryUnitOfWorkFactory({HealthLogRepository: logs, UserSettingsRepository: users}),
        clock=FixedClock(NOW),
        translator=JsonTranslator.from_dir(find_locales_dir()),
        memory=memory,
        default_locale="ru",
    )
    request = SkillRequest(
        task_id="t",
        context_id="c",
        text="устал от работы, 6 из 10",
        user_id=user,
        skill_id="log_mood",
        for_date=None,
        is_peer_call=False,
        params=params or {},
    )
    return handler, llm, logs, memory, request


async def test_stores_entry_with_legacy_keys_and_confirms() -> None:
    handler, llm, logs, memory, request = setup()
    llm.queue_structured(
        {
            "mood_score": 6,
            "energy": 4,
            "tags": ["усталость", "работа"],
            "summary": "tired from work",
        }
    )
    result = await handler(request, ())
    [row] = logs.rows[request.user_id]
    assert (row.type, row.agent, row.source) == ("mood", "mood", "manual")
    assert row.data == {
        "mood_score": 6,
        "energy": 4,
        "stress": None,
        "valence": None,
        "tags": ["усталость", "работа"],
        "raw_text": request.text,
        "source_skill": "log_mood",
    }
    assert result.output == "Записал настроение 6/10: усталость, работа."
    assert result.log_entry == request.text
    assert memory.items[0][3].text == request.text  # legacy remembered the message for log_mood


async def test_invalid_output_keeps_the_raw_text() -> None:
    handler, llm, logs, _, request = setup()
    llm.queue_structured(LLMInvalidOutput("{}", "bad"), LLMInvalidOutput("{}", "bad again"))
    result = await handler(request, ())
    [row] = logs.rows[request.user_id]
    assert row.data["source_skill"] == "log_mood_fallback"
    assert row.data["mood_score"] is None
    assert result.output == "Записал как есть — оценку не понял."


async def test_unavailable_model_stores_nothing() -> None:
    handler, llm, logs, _, request = setup()
    llm.queue_structured(LLMUnavailable("down"))
    result = await handler(request, ())
    assert result.failed
    assert logs.rows == {}
    assert result.log_entry is None


async def test_no_signal_stores_nothing() -> None:
    handler, llm, logs, _, request = setup()
    llm.queue_structured({"summary": "no mood signal"})
    result = await handler(request, ())
    assert logs.rows == {}
    assert result.output.startswith("Не увидел")


async def test_source_param_is_kept() -> None:
    handler, llm, logs, _, request = setup({"source": "evening_checkin"})
    llm.queue_structured({"mood_score": 8, "summary": "good"})
    await handler(request, ())
    assert logs.rows[request.user_id][0].source == "evening_checkin"


async def test_unavailable_during_repair_stores_nothing() -> None:
    handler, llm, logs, memory, request = setup()
    llm.queue_structured(LLMInvalidOutput("{}", "bad"), LLMUnavailable("down"))
    result = await handler(request, ())
    assert result.failed
    assert logs.rows == {}
    assert memory.items == []
    assert result.log_entry is None


async def test_repairs_invalid_scores_before_storing() -> None:
    handler, llm, logs, _, request = setup()
    llm.queue_structured(
        {"mood_score": 11, "summary": "bad"}, {"mood_score": "6", "summary": "tired"}
    )
    await handler(request, ())
    assert logs.rows[request.user_id][0].data["mood_score"] == 6
    assert len(llm.calls) == 2
    assert "previous answer was rejected" in llm.calls[1].user


async def test_english_confirmation_uses_user_locale() -> None:
    from dataclasses import replace

    handler, llm, logs, memory, request = setup()
    users = InMemoryUserSettings()
    users.seed(request.user_id, locale="en")
    handler = LogMood(
        llm=llm,
        uow=InMemoryUnitOfWorkFactory({HealthLogRepository: logs, UserSettingsRepository: users}),
        clock=FixedClock(NOW),
        translator=JsonTranslator.from_dir(find_locales_dir()),
        memory=memory,
        default_locale="ru",
    )
    llm.queue_structured({"energy": 3, "tags": [" Tired "], "summary": "tired"})
    result = await handler(replace(request, text="tired"), ())
    assert result.output == "Logged mood: tired."
