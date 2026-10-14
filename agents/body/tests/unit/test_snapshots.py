from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from body.application.data import BodyData
from body.composition import BODY_SPEC
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
USER = UUID(int=7)


@pytest.mark.parametrize("mode", ["get_latest_body", "analyze_body_trend"])
async def test_prompt_snapshot(mode: str, snapshot) -> None:  # type: ignore[no-untyped-def]
    logs, users = InMemoryHealthLogs(), InMemoryUserSettings()
    users.seed(USER, timezone="Europe/Lisbon", locale="ru")
    for i, (w, f) in enumerate([(82.5, 18.2), (83.1, 18.6), (83.4, 19.0)]):
        logs.seed(
            USER,
            HealthLogRow(
                "body_composition",
                NOW - timedelta(days=7 * i),
                {"weight_kg": w, "body_fat_pct": f, "bmr_kcal": 1800},
            ),
        )
    llm = FakeLLM()
    llm.queue_text("ok")
    handler = AnalysisSkill(
        spec=BODY_SPEC,
        mode=mode,
        data=BodyData(),
        llm=llm,
        uow=InMemoryUnitOfWorkFactory({HealthLogRepository: logs, UserSettingsRepository: users}),
        peers=FakePeerClient(
            {
                "nutrition": "deficit 300 kcal/day",
                "workout": "5 sessions last week, mostly strength.",
            }
        ),
        memory=InMemoryVectorMemory(),
        clock=FixedClock(NOW),
        translator=JsonTranslator.from_dir(find_locales_dir()),
        default_locale="ru",
    )
    await handler(
        SkillRequest(
            task_id="t",
            context_id="c",
            text="как меняется вес?",
            user_id=USER,
            skill_id=mode,
            for_date=None,
            is_peer_call=False,
        ),
        ("nutrition", "workout"),
    )
    snapshot(mode, f"{llm.calls[0].system}\n===== USER =====\n{llm.calls[0].user}\n")
