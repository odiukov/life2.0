from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from calendar_agent.application.feed import feed_items
from calendar_agent.application.skills import build_skills
from calendar_agent.domain.events import Event
from calendar_agent.testing import FakeGoogleCalendar, FakeGoogleOAuth
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.ports.credentials import CredentialStore
from shared.ports.users import UserSettingsRepository
from shared.skill_ids import Feed
from shared.testing.dashboard_golden import GOOGLE_EVENTS
from shared.testing.fakes import (
    FixedClock,
    InMemoryCredentialStore,
    InMemoryUnitOfWorkFactory,
    InMemoryUserSettings,
)
from shared.testing.feed_contract import assert_feed_contract

TR = JsonTranslator.from_dir(Path(__file__).resolve().parents[4] / "packages" / "i18n" / "locales")
NOW = datetime(2026, 10, 14, 6, 30, tzinfo=UTC)
KYIV = ZoneInfo("Europe/Kyiv")


def setup(connected: bool, google: FakeGoogleCalendar | None = None, locale: str = "en"):  # type: ignore[no-untyped-def]
    store, settings, user = InMemoryCredentialStore(), InMemoryUserSettings(), uuid4()
    settings.seed(user, timezone="Europe/Kyiv", locale=locale)
    if connected:
        store.rows[(user, "google_calendar")] = {
            "access_token": "a",
            "refresh_token": "r",
            "expires_at": "2026-10-14T08:00:00Z",
        }
    skills = build_skills(
        uow=InMemoryUnitOfWorkFactory({CredentialStore: store, UserSettingsRepository: settings}),
        google=google or FakeGoogleCalendar(GOOGLE_EVENTS),
        oauth=FakeGoogleOAuth(),
        clock=FixedClock(NOW),
        translator=TR,
        default_locale="en",
    )
    return skills, user


def req(user, day: str) -> SkillRequest:  # type: ignore[no-untyped-def]
    return SkillRequest("t", "c", "", user, Feed.EVENTS, None, False, {"date": day})


async def test_events_of_the_day_become_items() -> None:
    skills, user = setup(connected=True)
    result = await skills[Feed.EVENTS](req(user, "2026-10-14"), ())
    assert_feed_contract(result.data, date(2026, 10, 14), KYIV)
    assert result.data["items"]  # FakeGoogleCalendar's default day has events
    timed = [i for i in result.data["items"] if not i["text"].startswith("All day")]
    assert all(i["text"][2] == ":" for i in timed)  # "HH:MM title"


async def test_not_connected_calendar_is_an_empty_feed() -> None:
    skills, user = setup(connected=False)
    result = await skills[Feed.EVENTS](req(user, "2026-10-14"), ())
    assert not result.failed
    assert result.data == {"items": []}


async def test_google_outage_is_a_failure_code() -> None:
    google = FakeGoogleCalendar()
    google.unavailable = True
    skills, user = setup(connected=True, google=google)
    result = await skills[Feed.EVENTS](req(user, "2026-10-14"), ())
    assert result.failed
    assert result.output == "calendar_unavailable"


def test_local_day_overlap_boundaries() -> None:
    day = date(2026, 10, 14)
    start = datetime(2026, 10, 14, tzinfo=KYIV)

    def event(id, a, b):
        return Event(id, id, False, a, b, None, None)

    events = [
        event("overnight", start - timedelta(hours=1), start + timedelta(hours=1)),
        event("ended", start - timedelta(hours=2), start),
        event("tomorrow", start + timedelta(days=1), start + timedelta(days=1, hours=1)),
        Event("all", "", True, None, None, day, None),
        Event("past", "past", True, None, None, day - timedelta(days=1), None),
        Event("future", "future", True, None, None, day + timedelta(days=1), None),
    ]
    items = feed_items(events, day, KYIV, lambda key, **p: TR.t(key, "ru", **p))
    assert [i.id for i in items] == ["calendar:event:overnight", "calendar:event:all"]
    assert items[0].at == start
    assert items[0].text == "23:00 overnight"
    assert items[1].text == "Весь день: Без названия"


async def test_actual_skill_caps_events_and_localizes() -> None:
    google = FakeGoogleCalendar(
        [
            {
                "id": str(n),
                "summary": "",
                "start": {"date": "2026-10-14"},
                "end": {"date": "2026-10-15"},
            }
            for n in range(60)
        ]
    )
    skills, user = setup(True, google, locale="ru")
    result = await skills[Feed.EVENTS](req(user, "2026-10-14"), ())
    assert len(result.data["items"]) == 50
    assert all(i["text"] == "Весь день: Без названия" for i in result.data["items"])


async def test_multiday_all_day_event_uses_exclusive_end() -> None:
    google = FakeGoogleCalendar()

    async def list_events(*args, **kwargs):
        return [
            {
                "id": "spanning",
                "summary": "Trip",
                "start": {"date": "2026-10-13"},
                "end": {"date": "2026-10-15"},
            },
            {"id": "ended", "start": {"date": "2026-10-13"}, "end": {"date": "2026-10-14"}},
        ]

    google.list_events = list_events
    skills, user = setup(True, google)
    result = await skills[Feed.EVENTS](req(user, "2026-10-14"), ())
    assert [i["id"] for i in result.data["items"]] == ["calendar:event:spanning"]


def test_card_declares_feed_skill() -> None:
    from calendar_agent.adapters.a2a.card import SKILLS

    assert Feed.EVENTS in {skill.id for skill in SKILLS}
