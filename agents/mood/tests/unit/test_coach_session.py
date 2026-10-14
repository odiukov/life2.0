from datetime import UTC, datetime
from uuid import uuid4

from mood.application.coach_session import CoachSession
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.config import find_locales_dir
from shared.ports.health_logs import HealthLogRepository
from shared.ports.users import UserSettingsRepository
from shared.testing.fakes import (
    FakeLLM,
    FixedClock,
    InMemoryHealthLogs,
    InMemoryUnitOfWorkFactory,
    InMemoryUserSettings,
    InMemoryVectorMemory,
)

NOW = datetime(2026, 10, 13, 21, 0, tzinfo=UTC)


async def test_summarizes_the_transcript_and_stores_a_coach_entry() -> None:
    logs, users, llm = InMemoryHealthLogs(), InMemoryUserSettings(), FakeLLM()
    user = uuid4()
    llm.queue_structured(
        {
            "mood_score": 5,
            "stress": 7,
            "tags": ["work"],
            "summary": "Worked through deadline anxiety.\nNamed two triggers.\nPlanned a walk.",
        }
    )
    handler = CoachSession(
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
        text="",
        user_id=user,
        skill_id="coach_session",
        for_date=None,
        is_peer_call=False,
        params={"transcript": "coach: как ты? user: тревожно из-за дедлайна"},
    )
    result = await handler(request, ())
    [row] = logs.rows[user]
    assert (row.source, row.data["source_skill"], row.data["raw_text"]) == (
        "mood_agent",
        "coach_session",
        request.params["transcript"],
    )
    assert result.output.startswith("Worked through deadline anxiety.")
    assert "тревожно" in llm.calls[0].user


async def test_unavailable_coach_stores_nothing() -> None:
    from shared.ports.llm import LLMUnavailable

    logs, users, llm, memory = (
        InMemoryHealthLogs(),
        InMemoryUserSettings(),
        FakeLLM(),
        InMemoryVectorMemory(),
    )
    user = uuid4()
    llm.queue_structured(LLMUnavailable("down"))
    handler = CoachSession(
        llm=llm,
        uow=InMemoryUnitOfWorkFactory({HealthLogRepository: logs, UserSettingsRepository: users}),
        clock=FixedClock(NOW),
        translator=JsonTranslator.from_dir(find_locales_dir()),
        memory=memory,
        default_locale="ru",
    )
    result = await handler(
        SkillRequest(
            task_id="t",
            context_id="c",
            text="",
            user_id=user,
            skill_id="coach_session",
            for_date=None,
            is_peer_call=False,
            params={"transcript": "anxious"},
        ),
        (),
    )
    assert result.failed
    assert logs.rows == {}
    assert memory.items == []
