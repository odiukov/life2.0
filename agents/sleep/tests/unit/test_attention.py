from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

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
from sleep.application.attention import collect
from sleep.domain.attention import short_streak

TR = JsonTranslator.from_dir(Path(__file__).resolve().parents[4] / "packages" / "i18n" / "locales")
NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
TODAY = date(2026, 10, 16)
USER = uuid4()


def test_short_streak() -> None:
    y = TODAY - timedelta(days=1)
    assert short_streak({TODAY: 5 * 3600, y: 5 * 3600}, TODAY)
    assert not short_streak({TODAY: 5 * 3600, y: 7 * 3600}, TODAY)
    assert not short_streak({TODAY: 5 * 3600}, TODAY)  # last night unknown → no claim


def night(days_ago: int, hours: float, source: str = "garmin") -> HealthLogRow:
    at = NOW.replace(hour=4) - timedelta(days=days_ago)
    return HealthLogRow(
        "sleep_session", at, {"duration_seconds": int(hours * 3600)}, source, "sleep"
    )


async def run(*rows: HealthLogRow) -> list[dict]:  # type: ignore[type-arg]
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


async def test_two_short_nights_give_one_normal_item() -> None:
    [item] = await run(night(0, 5.5), night(1, 5), night(0, 8, source="SourceProxy"))
    assert (item["id"], item["level"]) == ("sleep:short:2026-10-16", "normal")
    assert item["action"] == {"type": "agent"}


async def test_a_long_night_clears_it() -> None:
    assert await run(night(0, 5.5), night(1, 7)) == []
