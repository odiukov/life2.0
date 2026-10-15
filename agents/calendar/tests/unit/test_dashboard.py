from calendar_agent.application.dashboard import CalendarCard, CalendarDetail
from calendar_agent.application.tokens import SERVICE
from calendar_agent.testing import FakeGoogleCalendar, FakeGoogleOAuth
from shared.a2a.request import SkillRequest
from shared.ports.credentials import CredentialStore
from shared.ports.users import UserSettingsRepository
from shared.skill_ids import Dashboard
from shared.testing import dashboard_golden as g
from shared.testing.fakes import FixedClock, InMemoryCredentialStore, InMemoryUnitOfWorkFactory


def handlers(google: FakeGoogleCalendar | None = None, connected: bool = True):
    store = InMemoryCredentialStore()
    if connected:
        store.rows[(g.USER_ID, SERVICE)] = {
            "access_token": "a",
            "refresh_token": "r",
            "expires_at": "2026-10-14T08:00:00Z",
        }
    uow = InMemoryUnitOfWorkFactory(
        {CredentialStore: store, UserSettingsRepository: g.memory_settings()}
    )
    deps = {
        "uow": uow,
        "google": google or FakeGoogleCalendar(g.GOOGLE_EVENTS),
        "oauth": FakeGoogleOAuth(),
        "clock": FixedClock(g.FROZEN_NOW),
    }
    return CalendarCard(**deps), CalendarDetail(**deps)


def req(skill: str) -> SkillRequest:
    return SkillRequest("t", "c", "", g.USER_ID, skill, None, False)


async def test_card_and_detail_match_the_goldens() -> None:
    card, detail = handlers()
    assert g.as_json((await card(req(Dashboard.CARD), ())).data) == g.expected_card("calendar")
    assert g.as_json((await detail(req(Dashboard.DETAIL), ())).data) == g.expected_detail(
        "calendar"
    )


async def test_card_is_empty_when_not_connected_or_down() -> None:
    card, _ = handlers(connected=False)
    assert (await card(req(Dashboard.CARD), ())).data == {
        "tile": None,
        "featured": None,
        "rings": {},
    }
    google = FakeGoogleCalendar(g.GOOGLE_EVENTS)
    google.unavailable = True
    card, _ = handlers(google)
    assert (await card(req(Dashboard.CARD), ())).data["tile"] is None
