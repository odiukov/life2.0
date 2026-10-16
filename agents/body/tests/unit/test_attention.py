from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from body.application.attention import collect
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.attention import AttentionSkill
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.users import UserSettingsRepository
from shared.skill_ids import Attention
from shared.testing.attention_contract import assert_attention_contract
from shared.testing.fakes import (
    FixedClock,
    InMemoryHealthLogs,
    InMemoryUnitOfWorkFactory,
    InMemoryUserSettings,
)

TR = JsonTranslator.from_dir(Path(__file__).resolve().parents[4] / "packages" / "i18n" / "locales")
NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
USER = uuid4()


def weigh_in(days_ago: int) -> HealthLogRow:
    return HealthLogRow(
        "body_composition", NOW - timedelta(days=days_ago), {"weight_kg": 80.1}, "vihealth", "body"
    )


async def run(*rows: HealthLogRow) -> list[dict[str, object]]:
    logs, settings = InMemoryHealthLogs(), InMemoryUserSettings()
    settings.seed(USER, timezone="Europe/Kyiv")
    for row in rows:
        logs.seed(USER, row)
    skill = AttentionSkill(
        uow=InMemoryUnitOfWorkFactory(
            {HealthLogRepository: logs, UserSettingsRepository: settings}
        ),
        clock=FixedClock(NOW),
        translator=TR,
        default_locale="en",
        collect=collect,
    )
    result = await skill(SkillRequest("t", "c", "", USER, Attention.ITEMS, None, False, {}), ())
    assert_attention_contract(result.data)
    return result.data["items"]  # type: ignore[index, return-value]


async def test_week_without_weigh_in() -> None:
    [item] = await run(weigh_in(8), weigh_in(20))
    assert item["id"] == f"body:weigh:{date(2026, 10, 8).isoformat()}"
    assert item["detail"] == "8 days since the last weigh-in"
    assert item["action"] == {"type": "task", "prompt": "My weight today:"}


async def test_never_weighed_or_recent_gives_nothing() -> None:
    assert await run() == []
    assert await run(weigh_in(2)) == []
