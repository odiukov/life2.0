from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from recovery.application.data import RecoveryData
from recovery.composition import RECOVERY_SPEC
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

NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
USER = UUID(int=8)


@pytest.mark.parametrize("mode", ["get_readiness", "analyze_recovery_trend", "get_recommendations"])
@pytest.mark.parametrize("with_peers", [True, False])
async def test_prompt_snapshot(mode: str, with_peers: bool, snapshot) -> None:  # type: ignore[no-untyped-def]
    logs, users = InMemoryHealthLogs(), InMemoryUserSettings()
    users.seed(USER, timezone="Europe/Lisbon")
    for i in range(10):
        day = NOW - timedelta(days=i)
        logs.seed(
            USER,
            HealthLogRow(
                "daily_stats",
                day.replace(hour=12),
                {"resting_hr": 52 + i % 3, "stress_avg": 28 + i},
                "garmin",
                "sleep",
            ),
        )
        logs.seed(
            USER,
            HealthLogRow(
                "hrv_status", day.replace(hour=6), {"hrv_rmssd": 50 - i % 4}, "garmin", "sleep"
            ),
        )
    llm = FakeLLM()
    llm.queue_text("ok")
    handler = AnalysisSkill(
        spec=RECOVERY_SPEC,
        mode=mode,
        data=RecoveryData(mode),
        llm=llm,
        uow=InMemoryUnitOfWorkFactory({HealthLogRepository: logs, UserSettingsRepository: users}),
        peers=FakePeerClient({"sleep": "short nights"}),
        memory=InMemoryVectorMemory(),
        clock=FixedClock(NOW),
        translator=JsonTranslator.from_dir(find_locales_dir()),
        default_locale="ru",
    )
    await handler(
        SkillRequest(
            task_id="t",
            context_id="c",
            text="готов к тренировке?",
            user_id=USER,
            skill_id=mode,
            for_date=None,
            is_peer_call=False,
        ),
        ("sleep",) if with_peers else (),
    )
    assert "autonomic recovery analyst" in llm.calls[0].system
    assert "GROUNDING RULES — strict:" in llm.calls[0].system
    assert ("drop a slash-mention right after the fact" in llm.calls[0].user) == with_peers
    snapshot(
        f"{mode}_{with_peers}", f"{llm.calls[0].system}\n===== USER =====\n{llm.calls[0].user}\n"
    )
