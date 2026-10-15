from datetime import UTC, date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from shared.a2a.request import SkillRequest
from shared.dashboard import (
    DashboardContext,
    DashboardSkill,
    fmt_duration,
    history_points,
    pg_round,
)
from shared.ports.users import UserSettings, UserSettingsRepository
from shared.testing.fakes import FixedClock, InMemoryUnitOfWorkFactory, InMemoryUserSettings

KYIV = ZoneInfo("Europe/Kyiv")


def test_rounding_matches_postgres_numeric() -> None:
    assert pg_round(2.5) == 3.0
    assert round(2.5) == 2
    assert pg_round(7.125, 2) == 7.13
    assert pg_round(-0.5) == -1.0


def test_context_days_follow_the_zone_across_dst() -> None:
    ctx = DashboardContext(
        uuid4(), UserSettings(KYIV, None), datetime(2026, 10, 25, 22, 30, tzinfo=UTC)
    )
    assert ctx.today == date(2026, 10, 26)
    assert ctx.yesterday == date(2026, 10, 25)
    start, end = ctx.bounds(date(2026, 10, 25))  # the DST night: 25 hours long
    assert (end - start).total_seconds() == 25 * 3600
    assert ctx.last_days(3) == [date(2026, 10, 24), date(2026, 10, 25), date(2026, 10, 26)]


def test_formatting() -> None:
    assert fmt_duration(27000) == "7h 30m"
    assert fmt_duration(0) == "0h 0m"
    points = history_points(
        [date(2026, 10, 13), date(2026, 10, 14)],
        {date(2026, 10, 14): 2.0},
        lambda v: f"{v:g}" if v else "—",
    )
    assert points == [
        {"date": "2026-10-13", "value": 0.0, "label": "—"},
        {"date": "2026-10-14", "value": 2.0, "label": "2"},
    ]


async def test_skill_passes_the_users_settings_and_clock() -> None:
    settings = InMemoryUserSettings()
    user = uuid4()
    settings.seed(user, timezone="Europe/Kyiv")
    seen = {}

    async def build(tx, ctx):  # type: ignore[no-untyped-def]
        seen["today"] = ctx.today
        return {"ok": True}

    skill = DashboardSkill(
        uow=InMemoryUnitOfWorkFactory({UserSettingsRepository: settings}),
        clock=FixedClock(datetime(2026, 10, 13, 22, tzinfo=UTC)),
        build=build,
        name="card",
    )
    result = await skill(SkillRequest("t", "c", "", user, "dashboard.card", None, False), ())
    assert result.data == {"ok": True}
    assert seen["today"] == date(2026, 10, 14)
