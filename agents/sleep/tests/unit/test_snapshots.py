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
from sleep.application.data import SleepData
from sleep.composition import SLEEP_SPEC

NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
USER = UUID(int=9)


@pytest.mark.parametrize("mode", ["analyze_sleep", "get_sleep_recommendations"])
async def test_prompt_snapshot(mode: str, snapshot) -> None:  # type: ignore[no-untyped-def]
    logs, users = InMemoryHealthLogs(), InMemoryUserSettings()
    users.seed(USER, timezone="Europe/Lisbon")
    for i, (dur, score) in enumerate([(25200, 81), (23400, 72), (27000, 85)]):
        logs.seed(
            USER,
            HealthLogRow(
                "sleep_session",
                NOW - timedelta(days=i, hours=10),
                {"duration_seconds": dur, "score": score},
                "garmin",
                "sleep",
            ),
        )
    logs.seed(
        USER,
        HealthLogRow(
            "sleep_session",
            NOW - timedelta(hours=9),
            {"duration_seconds": 27000, "quality": 4},
            "chat",
            "sleep",
        ),
    )
    llm = FakeLLM()
    llm.queue_text("ok")
    peers = FakePeerClient({"workout": "evening run 10k"})
    handler = AnalysisSkill(
        spec=SLEEP_SPEC,
        mode=mode,
        data=SleepData(),
        llm=llm,
        uow=InMemoryUnitOfWorkFactory({HealthLogRepository: logs, UserSettingsRepository: users}),
        peers=peers,
        memory=InMemoryVectorMemory(),
        clock=FixedClock(NOW),
        translator=JsonTranslator.from_dir(find_locales_dir()),
        default_locale="ru",
    )
    await handler(
        SkillRequest(
            task_id="t",
            context_id="c",
            text="почему я не высыпаюсь?",
            user_id=USER,
            skill_id=mode,
            for_date=None,
            is_peer_call=False,
        ),
        ("workout",),
    )
    assert peers.calls[0]["for_date"] == date(2026, 10, 12)
    snapshot(mode, f"{llm.calls[0].system}\n===== USER =====\n{llm.calls[0].user}\n")
