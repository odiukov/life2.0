from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from mood.application.attention import collect
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


def checkin(days_ago: int) -> HealthLogRow:
    return HealthLogRow("mood", NOW - timedelta(days=days_ago), {"score": 7}, "chat", "mood")


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


async def test_three_days_without_checkin() -> None:
    [item] = await run(checkin(3), checkin(9))
    assert item["id"] == f"mood:checkin:{date(2026, 10, 13).isoformat()}"
    assert item["detail"] == "3 days since the last check-in"
    assert item["action"] == {"type": "task", "prompt": "My mood today:"}


async def test_never_checked_in_or_recent_gives_nothing() -> None:
    assert await run() == []
    assert await run(checkin(2)) == []
