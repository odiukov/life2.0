from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from calendar_agent.domain.changes import InvalidChange, google_body, parse_change
from calendar_agent.domain.events import day_shape, event_dto, event_line, normalize, title_matches
from shared.testing.dashboard_golden import GOOGLE_EVENTS

KYIV = ZoneInfo("Europe/Kyiv")
NY = ZoneInfo("America/New_York")


def events(zone: ZoneInfo = KYIV):
    return [e for r in GOOGLE_EVENTS if (e := normalize(r, zone))]


def test_normalize_timed_and_all_day() -> None:
    standup, *_, birthday = events()
    assert standup.summary == "Standup"
    assert standup.etag == '"3001"'
    assert not standup.all_day
    assert standup.start == datetime(2026, 10, 14, 7, 0, tzinfo=UTC)
    assert birthday.all_day
    assert birthday.day == date(2026, 10, 14)
    assert birthday.start is None
    assert normalize({"summary": "x"}, KYIV) is None
    assert normalize(
        {"start": {"dateTime": "2026-10-14T10:00:00"}, "end": {"dateTime": "2026-10-14T11:00:00"}},
        KYIV,
    ).start == datetime(2026, 10, 14, 7, tzinfo=UTC)


def test_day_shape_matches_the_legacy_shape() -> None:
    now = datetime(2026, 10, 14, 6, 30, tzinfo=UTC)  # 09:30 in Kyiv
    shape = day_shape(events(), date(2026, 10, 14), now, KYIV)
    assert shape == {
        "events_count": 3,
        "morning_count": 1,
        "afternoon_count": 1,
        "evening_count": 1,
        "busiest_hour": "10:00-11:00",
        "first_free_slot_start": "09:30",
        "first_free_slot_len_min": 30,
        "all_day_events": ["Mom's birthday"],
    }


def test_day_shape_uses_the_users_zone() -> None:
    now = datetime(2026, 10, 14, 6, 30, tzinfo=UTC)  # 02:30 in New York
    shape = day_shape(events(NY), date(2026, 10, 14), now, NY)
    # The same events at 03:00, 07:00 and 12:00 New York time.
    assert shape is not None
    assert (
        shape["morning_count"],
        shape["afternoon_count"],
        shape["evening_count"],
    ) == (2, 1, 0)
    assert shape["all_day_events"] == ["Mom's birthday"]


def test_day_shape_is_none_without_events() -> None:
    assert day_shape([], date(2026, 10, 14), datetime(2026, 10, 14, tzinfo=UTC), KYIV) is None


@pytest.mark.parametrize(
    ("query", "summary", "expected"),
    [
        ("gym", "Gym", True),
        ("удали встречу design review", "Design review", True),
        ("standup", "Design review", False),
        ("", "Gym", False),
    ],
)
def test_title_matching(query: str, summary: str, expected: bool) -> None:
    assert title_matches(query, summary) is expected


def test_event_line_and_dto() -> None:
    gym = events()[2]
    assert event_line(gym, KYIV) == "• 19:00-20:00: Gym (event_id: ev-gym)"
    assert event_dto(gym)["etag"] == '"3003"'


def test_parse_change_validates_times() -> None:
    change = parse_change(
        {
            "op": "create",
            "fields": {
                "summary": "Dentist",
                "start": "2026-10-15T09:00:00+03:00",
                "end": "2026-10-15T10:00:00+03:00",
            },
        }
    )
    assert google_body(change.fields) == {
        "summary": "Dentist",
        "start": {"dateTime": "2026-10-15T09:00:00+03:00"},
        "end": {"dateTime": "2026-10-15T10:00:00+03:00"},
    }
    for bad in (
        {
            "op": "create",
            "fields": {
                "summary": "x",
                "start": "2026-10-15T09:00:00",
                "end": "2026-10-15T10:00:00",
            },
        },
        {
            "op": "create",
            "fields": {
                "summary": "x",
                "start": "2026-10-15T10:00:00+03:00",
                "end": "2026-10-15T09:00:00+03:00",
            },
        },
        {
            "op": "create",
            "fields": {"start": "2026-10-15T09:00:00+03:00", "end": "2026-10-15T10:00:00+03:00"},
        },
        {"op": "rename", "fields": {}},
        {"op": "update", "fields": {"colorId": "5"}},
    ):
        with pytest.raises(InvalidChange):
            parse_change(bad)


def test_title_matching_accepts_injected_stopwords() -> None:
    assert not title_matches(
        "удали встреча врача", "Встреча проекта", frozenset({"удали", "встреча"})
    )
    assert title_matches(
        "удали встреча проекта", "Встреча проекта", frozenset({"удали", "встреча"})
    )
