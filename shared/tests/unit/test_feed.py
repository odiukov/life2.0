from datetime import UTC, date, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.dashboard import DashboardContext
from shared.feed import (
    MAX_ITEMS,
    FeedContext,
    FeedItem,
    FeedSkill,
    InvalidFeedDate,
    clip,
    day_rows,
    duration_text,
    insight_items,
    prefer_sources,
    requested_day,
    row_id,
)
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.users import UserSettings, UserSettingsRepository
from shared.skill_ids import Feed
from shared.testing.fakes import (
    FixedClock,
    InMemoryHealthLogs,
    InMemoryUnitOfWorkFactory,
    InMemoryUserSettings,
)
from shared.testing.feed_contract import assert_feed_contract

KYIV = ZoneInfo("Europe/Kyiv")
NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)  # 12:00 in Kyiv
TR = JsonTranslator(
    {
        "en": {"feed": {"duration": {"hm": "{h} h {m} min", "m": "{m} min"}}, "x": "hello {name}"},
        "ru": {"feed": {"duration": {"hm": "{h} ч {m} мин", "m": "{m} мин"}}, "x": "привет {name}"},
    }
)


def ctx(day: date = date(2026, 10, 14), locale: str = "en", user=None) -> FeedContext:  # type: ignore[no-untyped-def]
    return FeedContext(
        DashboardContext(user or uuid4(), UserSettings(KYIV, locale), NOW), day, locale, TR
    )


def req(user, **params) -> SkillRequest:  # type: ignore[no-untyped-def]
    return SkillRequest("t", "c", "", user, Feed.EVENTS, None, False, params)


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({}, date(2026, 10, 14)),
        ({"date": "2026-10-14"}, date(2026, 10, 14)),
        ({"date": "2026-09-14"}, date(2026, 9, 14)),
    ],
)
def test_requested_day_accepts_today_and_up_to_thirty_days_back(params, expected) -> None:  # type: ignore[no-untyped-def]
    assert requested_day(params, date(2026, 10, 14)) == expected


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ("2026-09-13", "date_out_of_range"),
        ("2026-10-15", "date_out_of_range"),
        ("yesterday", "invalid_params"),
        (20261014, "invalid_params"),
    ],
)
def test_requested_day_rejects_bad_dates(value, code) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(InvalidFeedDate) as caught:
        requested_day({"date": value}, date(2026, 10, 14))
    assert caught.value.code == code


def test_clip_makes_one_short_line() -> None:
    assert clip("a\n  b\tc") == "a b c"
    long = clip("x" * 200)
    assert len(long) == 140
    assert long.endswith("…")


def test_row_id_is_stable_and_names_the_source() -> None:
    row = HealthLogRow(
        "sleep_session", datetime(2026, 10, 14, 4, 40, tzinfo=UTC), {}, "garmin", "sleep"
    )
    assert row_id("sleep", row) == "sleep:sleep_session:garmin:2026-10-14T04:40:00+00:00"


def test_duration_text_is_localized() -> None:
    assert duration_text(ctx(), 27600) == "7 h 40 min"
    assert duration_text(ctx(locale="ru"), 2700) == "45 мин"


async def test_day_rows_follow_the_users_zone() -> None:
    """Kyiv 14 Oct = [13 Oct 21:00 UTC, 14 Oct 21:00 UTC)."""
    user = uuid4()
    logs = InMemoryHealthLogs()
    inside_early = datetime(2026, 10, 13, 21, 30, tzinfo=UTC)  # 00:30 Kyiv, 14 Oct
    inside_late = datetime(2026, 10, 14, 20, 30, tzinfo=UTC)  # 23:30 Kyiv, 14 Oct
    outside = datetime(2026, 10, 14, 21, 0, tzinfo=UTC)  # 00:00 Kyiv, 15 Oct
    before = datetime(2026, 10, 13, 20, 59, tzinfo=UTC)  # 23:59 Kyiv, 13 Oct
    for at in (inside_early, inside_late, outside, before):
        logs.seed(user, HealthLogRow("mood", at, {"mood_score": 7}, "chat", "mood"))
    uow = InMemoryUnitOfWorkFactory({HealthLogRepository: logs})
    async with uow.for_user(user) as tx:
        rows = await day_rows(tx, ctx(user=user), types=["mood"], agent="mood")
    assert sorted(r.recorded_at for r in rows) == [inside_early, inside_late]


def test_prefer_sources_keeps_the_best_source_of_a_duplicate() -> None:
    t = datetime(2026, 10, 14, 5, 0, tzinfo=UTC)
    garmin = HealthLogRow("sleep_session", t, {}, "garmin", "sleep")
    apple = HealthLogRow("sleep_session", t + timedelta(minutes=20), {}, "SourceProxy", "sleep")
    nap = HealthLogRow("sleep_session", t + timedelta(hours=9), {}, "SourceProxy", "sleep")
    kept = prefer_sources(
        [apple, nap, garmin],
        ("garmin", "SourceProxy"),
        same=lambda a, b: abs(a.recorded_at - b.recorded_at) <= timedelta(hours=3),
    )
    assert kept == [garmin, nap]


def test_insight_items_only_for_today_and_only_when_present() -> None:
    assert insight_items("sleep", ctx(), {"insight": "Deep sleep best this week"}) == [
        FeedItem("sleep:insight:2026-10-14", NOW, "insight", "Deep sleep best this week")
    ]
    assert insight_items("sleep", ctx(day=date(2026, 10, 13)), {"insight": "old"}) == []
    assert insight_items("sleep", ctx(), {"insight": None}) == []
    assert insight_items("sleep", ctx(), {"insight": "   "}) == []


async def test_skill_sorts_newest_first_caps_and_falls_back_to_the_default_locale() -> None:
    user = uuid4()
    settings = InMemoryUserSettings()
    settings.seed(user, timezone="Europe/Kyiv")
    seen: dict[str, object] = {}

    async def collect(tx, c):  # type: ignore[no-untyped-def]
        seen["locale"], seen["day"] = c.locale, c.day
        base = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)
        return [
            FeedItem(f"x:{i}", base + timedelta(minutes=i), "event", c.t("x", name=str(i)))
            for i in range(60)
        ]

    skill = FeedSkill(
        uow=InMemoryUnitOfWorkFactory({UserSettingsRepository: settings}),
        clock=FixedClock(NOW),
        translator=TR,
        default_locale="ru",
        collect=collect,
    )
    result = await skill(req(user), ())
    items = result.data["items"]  # type: ignore[index]
    assert seen == {"locale": "ru", "day": date(2026, 10, 14)}
    assert len(items) == MAX_ITEMS
    assert items[0]["id"] == "x:59"
    assert items[0]["text"] == "привет 59"
    assert_feed_contract(result.data, date(2026, 10, 14), KYIV)


async def test_skill_reports_bad_dates_as_codes() -> None:
    settings = InMemoryUserSettings()
    user = uuid4()
    settings.seed(user, timezone="Europe/Kyiv")

    async def collect(tx, c):  # type: ignore[no-untyped-def]
        raise AssertionError("not reached")

    skill = FeedSkill(
        uow=InMemoryUnitOfWorkFactory({UserSettingsRepository: settings}),
        clock=FixedClock(NOW),
        translator=TR,
        default_locale="en",
        collect=collect,
    )
    result = await skill(req(user, date="2026-10-15"), ())
    assert result.failed
    assert result.output == "date_out_of_range"


def test_contract_rejects_items_outside_the_day() -> None:
    bad = {
        "items": [{"id": "a", "at": "2026-10-14T21:30:00+00:00", "kind": "event", "text": "late"}]
    }
    with pytest.raises(AssertionError):
        assert_feed_contract(bad, date(2026, 10, 14), KYIV)


@pytest.mark.parametrize("value", ["20261014", "2026-W42-3", "2026-W42", "2026-10-14 ", "2026-1-4"])
def test_requested_day_requires_canonical_calendar_date(value: str) -> None:
    with pytest.raises(InvalidFeedDate, match="invalid_params"):
        requested_day({"date": value}, date(2026, 10, 14))


def test_prefer_sources_preserves_distinct_events_from_the_same_source() -> None:
    at = datetime(2026, 10, 14, 5, tzinfo=UTC)
    first = HealthLogRow("sleep_session", at, {}, "garmin", "sleep")
    second = HealthLogRow("sleep_session", at + timedelta(hours=1), {}, "garmin", "sleep")
    duplicate = HealthLogRow(
        "sleep_session", at + timedelta(minutes=20), {}, "SourceProxy", "sleep"
    )
    kept = prefer_sources(
        [second, duplicate, first],
        ("garmin", "SourceProxy"),
        same=lambda a, b: abs(a.recorded_at - b.recorded_at) <= timedelta(hours=3),
    )
    assert kept == [first, second]
