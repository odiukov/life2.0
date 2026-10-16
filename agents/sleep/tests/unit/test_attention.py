from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

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
KYIV = ZoneInfo("Europe/Kyiv")


def test_short_streak() -> None:
    y = TODAY - timedelta(days=1)
    assert short_streak({TODAY: 5 * 3600, y: 5 * 3600}, TODAY)
    assert not short_streak({TODAY: 5 * 3600, y: 7 * 3600}, TODAY)
    assert not short_streak({TODAY: 5 * 3600}, TODAY)  # last night unknown → no claim


def night(
    wake_days_ago: int,
    hours: float,
    source: str = "garmin",
    *,
    bed: tuple[int, int] = (23, 30),
    end_time: bool = True,
) -> HealthLogRow:
    """A start-anchored row, as Garmin and chat store it: recorded_at is the local bedtime."""
    wake_day = TODAY - timedelta(days=wake_days_ago)
    start = datetime.combine(wake_day - timedelta(days=1), datetime.min.time(), KYIV).replace(
        hour=bed[0], minute=bed[1]
    )
    end = start + timedelta(hours=hours)
    data: dict[str, object] = {
        "duration_seconds": int(hours * 3600),
        "start_time": start.isoformat(),
    }
    if end_time:
        data["end_time"] = end.isoformat()
    return HealthLogRow("sleep_session", start.astimezone(UTC), data, source, "sleep")


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


async def test_start_anchored_nights_key_by_wake_date() -> None:
    # 23:30 Oct14 -> 05:00 Oct15 and 23:30 Oct15 -> 05:00 Oct16, Kyiv.
    [item] = await run(night(0, 5.5), night(1, 5.5))
    assert item["id"] == "sleep:short:2026-10-16"


async def test_wake_date_falls_back_to_start_plus_duration() -> None:
    [item] = await run(night(0, 5.5, end_time=False), night(1, 5.5, end_time=False))
    assert item["id"] == "sleep:short:2026-10-16"


async def test_wake_date_uses_the_local_midnight_boundary() -> None:
    # Bed 18:00 Oct15 + 5.5 h -> wake 23:30 Oct15 local: that is yesterday's night, not today's.
    assert await run(night(0, 5.5, bed=(18, 0)), night(1, 5.5)) == []
    # Bed 19:00 Oct15 + 5.5 h -> wake 00:30 Oct16 local (21:30 UTC Oct15): today's night.
    [item] = await run(night(0, 5.5, bed=(19, 0)), night(1, 5.5))
    assert item["id"] == "sleep:short:2026-10-16"


async def test_yesterday_missing_gives_nothing() -> None:
    assert await run(night(0, 5)) == []
    assert await run(night(0, 5), night(2, 5)) == []
