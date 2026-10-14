from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
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
from workout.application.data import WorkoutData
from workout.composition import WORKOUT_SPEC

NOW = datetime(2026, 10, 13, 17, 0, tzinfo=UTC)
USER = UUID(int=10)


def handler(llm: FakeLLM, mode: str) -> AnalysisSkill:
    logs, users = InMemoryHealthLogs(), InMemoryUserSettings()
    users.seed(USER, timezone="Europe/Lisbon")
    logs.seed(
        USER,
        HealthLogRow(
            "activity",
            NOW - timedelta(days=1),
            {"activity_type": "running", "duration_seconds": 3000, "distance_meters": 10000},
            "garmin",
            "workout",
        ),
    )
    logs.seed(
        USER,
        HealthLogRow(
            "activity",
            NOW - timedelta(days=3),
            {"activity_type": "strength_training", "duration_seconds": 3600, "effort": 8},
            "chat",
            "workout",
        ),
    )
    logs.seed(
        USER,
        HealthLogRow(
            "body_composition",
            NOW - timedelta(days=2),
            {"weight_kg": 82.5, "body_fat_pct": 18.2},
            "vihealth",
            "body",
        ),
    )
    return AnalysisSkill(
        spec=WORKOUT_SPEC,
        mode=mode,
        data=WorkoutData(),
        llm=llm,
        uow=InMemoryUnitOfWorkFactory({HealthLogRepository: logs, UserSettingsRepository: users}),
        peers=FakePeerClient({"recovery": "neutral"}),
        memory=InMemoryVectorMemory(),
        clock=FixedClock(NOW),
        translator=JsonTranslator.from_dir(find_locales_dir()),
        default_locale="ru",
    )


@pytest.mark.parametrize("mode", ["analyze_workout", "get_workout_recommendations"])
async def test_prompt_snapshot(mode: str, snapshot) -> None:  # type: ignore[no-untyped-def]
    llm = FakeLLM()
    llm.queue_text("ok")
    await handler(llm, mode)(
        SkillRequest(
            task_id="t",
            context_id="c",
            text="что делать завтра?",
            user_id=USER,
            skill_id=mode,
            for_date=None,
            is_peer_call=False,
        ),
        ("recovery",),
    )
    snapshot(mode, f"{llm.calls[0].system}\n===== USER =====\n{llm.calls[0].user}\n")


async def test_peer_call_with_for_date_gets_the_focus_section() -> None:
    llm = FakeLLM()
    llm.queue_text("ok")
    await handler(llm, "analyze_workout")(
        SkillRequest(
            task_id="t",
            context_id="c",
            text="",
            user_id=USER,
            skill_id="analyze_workout",
            for_date=date(2026, 10, 12),
            is_peer_call=True,
        ),
        (),
    )
    assert "## Peer-consult focus date: 2026-10-12" in llm.calls[0].user
