from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from mood.application.data import MoodData
from mood.composition import MOOD_SPEC
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.analysis.skill import AnalysisSkill
from shared.config import find_locales_dir
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.users import UserSettingsRepository
from shared.testing.fakes import (
    FakeLLM,
    FakePeerClient,
    FixedClock,
    InMemoryHealthLogs,
    InMemoryUnitOfWorkFactory,
    InMemoryUserSettings,
    InMemoryVectorMemory,
)

NOW = datetime(2026, 10, 13, 18, 0, tzinfo=UTC)
USER = UUID(int=11)


@pytest.mark.parametrize("mode", ["analyze_mood", "get_mood_recommendations"])
async def test_prompt_snapshot(mode: str, snapshot) -> None:  # type: ignore[no-untyped-def]
    logs, users = InMemoryHealthLogs(), InMemoryUserSettings()
    users.seed(USER, timezone="Europe/Lisbon")
    for i, (score, tags) in enumerate([(6, ["work"]), (4, ["tired", "work"]), (7, ["calm"])]):
        logs.seed(
            USER,
            HealthLogRow(
                "mood",
                NOW - timedelta(days=i),
                {"mood_score": score, "tags": tags, "raw_text": "…"},
                "manual",
                "mood",
            ),
        )
    llm = FakeLLM()
    llm.queue_text("ok")
    handler = AnalysisSkill(
        spec=MOOD_SPEC,
        mode=mode,
        data=MoodData(mode),
        llm=llm,
        uow=InMemoryUnitOfWorkFactory({HealthLogRepository: logs, UserSettingsRepository: users}),
        peers=FakePeerClient({"sleep": "two short nights"}),
        memory=InMemoryVectorMemory(),
        clock=FixedClock(NOW),
        translator=JsonTranslator.from_dir(find_locales_dir()),
        default_locale="ru",
    )
    await handler(
        SkillRequest(
            task_id="t",
            context_id="c",
            text="почему я устаю?",
            user_id=USER,
            skill_id=mode,
            for_date=None,
            is_peer_call=False,
        ),
        ("sleep",),
    )
    snapshot(mode, f"{llm.calls[0].system}\n===== USER =====\n{llm.calls[0].user}\n")
