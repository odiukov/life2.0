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
from workout.application.attention import collect
from workout.domain.attention import quiet_days

LOCALES = Path(__file__).resolve().parents[4] / "packages" / "i18n" / "locales"
TR = JsonTranslator.from_dir(LOCALES)
NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
TODAY = date(2026, 10, 16)
USER = uuid4()


def test_quiet_days_rule() -> None:
    d = lambda n: TODAY - timedelta(days=n)  # noqa: E731
    assert quiet_days([d(4), d(10)], TODAY) == 4
    assert quiet_days([d(3), d(10)], TODAY) is None  # trained 3 days ago
    assert quiet_days([d(9)], TODAY) is None  # only one workout in 30 days
    assert quiet_days([d(9), d(9)], TODAY) is None  # same day twice is one day
    assert quiet_days([], TODAY) is None


def activity(days_ago: int) -> HealthLogRow:
    at = NOW - timedelta(days=days_ago)
    return HealthLogRow("activity", at, {"name": "Run"}, "garmin", "workout")


async def run(*rows: HealthLogRow, locale: str = "en") -> list[dict]:  # type: ignore[type-arg]
    logs, settings = InMemoryHealthLogs(), InMemoryUserSettings()
    settings.seed(USER, timezone="Europe/Kyiv", locale=locale)
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


async def test_plan_item_after_four_quiet_days() -> None:
    [item] = await run(activity(5), activity(12))
    assert item["id"] == f"workout:plan:{(TODAY - timedelta(days=5)).isoformat()}"
    assert (item["level"], item["text"], item["detail"]) == (
        "high",
        "Plan a workout",
        "5 days without training",
    )
    assert item["action"] == {
        "type": "task",
        "prompt": "Help me plan a workout for the next few days",
    }


async def test_no_item_for_recent_training_or_rows_of_other_agents() -> None:
    assert await run(activity(1), activity(8)) == []
    other = HealthLogRow("activity", NOW - timedelta(days=6), {}, "garmin", "nutrition")
    assert await run(other, activity(12)) == []
