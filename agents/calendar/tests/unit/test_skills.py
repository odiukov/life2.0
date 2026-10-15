from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from calendar_agent.application.skills import build_skills
from calendar_agent.application.tokens import SERVICE
from calendar_agent.testing import FakeGoogleCalendar, FakeGoogleOAuth
from shared.a2a.proposals import from_data
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.config import find_locales_dir
from shared.ports.credentials import CredentialStore
from shared.ports.users import UserSettingsRepository
from shared.skill_ids import Calendar
from shared.testing.dashboard_golden import GOOGLE_EVENTS
from shared.testing.fakes import (
    FixedClock,
    InMemoryCredentialStore,
    InMemoryUnitOfWorkFactory,
    InMemoryUserSettings,
)

NOW = datetime(2026, 10, 14, 6, 30, tzinfo=UTC)


@pytest.fixture
def env():
    store, settings = InMemoryCredentialStore(), InMemoryUserSettings()
    uow = InMemoryUnitOfWorkFactory({CredentialStore: store, UserSettingsRepository: settings})
    google, oauth = FakeGoogleCalendar(GOOGLE_EVENTS), FakeGoogleOAuth()
    skills = build_skills(
        uow=uow,
        google=google,
        oauth=oauth,
        clock=FixedClock(NOW),
        translator=JsonTranslator.from_dir(find_locales_dir()),
        default_locale="ru",
    )
    user = uuid4()
    settings.seed(user, timezone="Europe/Kyiv", locale="ru")
    store.rows[(user, SERVICE)] = {
        "access_token": "a",
        "refresh_token": "r",
        "expires_at": (NOW + timedelta(hours=1)).isoformat(),
    }
    return skills, google, store, user


def req(user, skill: str, **params) -> SkillRequest:
    return SkillRequest("t", "c", "", user, skill, None, False, params=params)


async def test_list_returns_lines_for_the_model_and_dtos(env) -> None:
    skills, _, _, user = env
    result = await skills[Calendar.LIST](req(user, Calendar.LIST, day="2026-10-14"), ())
    assert result.output.splitlines()[0] == "Calendar events for 2026-10-14:"
    assert "• 19:00-20:00: Gym (event_id: ev-gym)" in result.output
    assert [e["id"] for e in result.data["events"]] == [
        "ev-standup",
        "ev-review",
        "ev-gym",
        "ev-birthday",
    ]


async def test_delete_by_title_proposes_with_the_etag(env) -> None:
    skills, google, _, user = env
    result = await skills[Calendar.PROPOSE](
        req(user, Calendar.PROPOSE, op="delete", title="gym", day="2026-10-14"), ()
    )
    proposal = from_data(result.data)
    assert proposal is not None
    assert proposal.action == "calendar.delete"
    assert proposal.payload == {
        "op": "delete",
        "event_id": "ev-gym",
        "etag": '"3003"',
        "fields": {},
    }
    assert "Gym" in proposal.summary
    assert "19:00" in proposal.summary
    assert "ev-gym" in google.events  # nothing changed yet


async def test_ambiguous_title_asks_back_instead_of_proposing(env) -> None:
    skills, google, _, user = env
    google.events["ev-gym2"] = {
        **google.events["ev-gym"],
        "id": "ev-gym2",
        "summary": "Gym with Ana",
    }
    result = await skills[Calendar.PROPOSE](
        req(user, Calendar.PROPOSE, op="delete", title="gym", day="2026-10-14"), ()
    )
    assert result.data["kind"] == "ambiguous"
    assert len(result.data["candidates"]) == 2


async def test_unknown_title_lists_what_is_visible(env) -> None:
    skills, _, _, user = env
    result = await skills[Calendar.PROPOSE](
        req(user, Calendar.PROPOSE, op="delete", title="dentist", day="2026-10-14"), ()
    )
    assert result.data["kind"] == "not_found"
    assert len(result.data["visible"]) == 4


async def test_apply_uses_if_match_and_refuses_changed_events(env) -> None:
    skills, google, _, user = env
    proposed = from_data(
        (
            await skills[Calendar.PROPOSE](
                req(
                    user,
                    Calendar.PROPOSE,
                    op="update",
                    event_id="ev-gym",
                    fields={"summary": "Gym (legs)"},
                ),
                (),
            )
        ).data
    )
    assert proposed is not None
    google.events["ev-gym"]["etag"] = '"9999"'  # someone edited it in Google in the meantime
    changed = await skills[Calendar.APPLY](
        req(user, Calendar.APPLY, payload=dict(proposed.payload)), ()
    )
    assert changed.failed
    assert changed.output == "changed_since_proposal"
    assert google.events["ev-gym"]["summary"] == "Gym"


async def test_apply_create_and_delete(env) -> None:
    skills, google, _, user = env
    created = from_data(
        (
            await skills[Calendar.PROPOSE](
                req(
                    user,
                    Calendar.PROPOSE,
                    op="create",
                    fields={
                        "summary": "Dentist",
                        "start": "2026-10-15T09:00:00+03:00",
                        "end": "2026-10-15T10:00:00+03:00",
                    },
                ),
                (),
            )
        ).data
    )
    done = await skills[Calendar.APPLY](
        req(user, Calendar.APPLY, payload=dict(created.payload)), ()
    )
    assert done.data == {"status": "applied", "event": {"id": "new-5", "summary": "Dentist"}}
    deleted = from_data(
        (
            await skills[Calendar.PROPOSE](
                req(user, Calendar.PROPOSE, op="delete", event_id="ev-standup"), ()
            )
        ).data
    )
    await skills[Calendar.APPLY](req(user, Calendar.APPLY, payload=dict(deleted.payload)), ())
    assert "ev-standup" not in google.events


@pytest.mark.parametrize(
    ("skill", "params", "code"),
    [
        (Calendar.LIST, {"day": "14.10.2026"}, "invalid_params"),
        (Calendar.PROPOSE, {"op": "delete"}, "invalid_params"),
        (Calendar.PROPOSE, {"op": "create", "fields": {"summary": "x"}}, "invalid_params"),
        (Calendar.APPLY, {"payload": {"op": "delete"}}, "invalid_params"),
        (Calendar.PROPOSE, {"op": "delete", "event_id": "nope"}, "not_found"),
    ],
)
async def test_bad_input_fails_with_codes(env, skill, params, code) -> None:
    skills, _, _, user = env
    result = await skills[skill](req(user, skill, **params), ())
    assert result.failed
    assert result.output == code


async def test_not_connected_and_unavailable(env) -> None:
    skills, google, store, user = env
    google.unavailable = True
    down = await skills[Calendar.LIST](req(user, Calendar.LIST, day="2026-10-14"), ())
    assert down.failed
    assert down.output == "calendar_unavailable"
    del store.rows[(user, SERVICE)]
    missing = await skills[Calendar.LIST](req(user, Calendar.LIST, day="2026-10-14"), ())
    assert missing.failed
    assert missing.output == "not_connected"


async def test_connect_status_disconnect(env) -> None:
    skills, _, store, _ = env
    other = uuid4()
    assert (await skills[Calendar.STATUS](req(other, Calendar.STATUS), ())).data == {
        "connected": False
    }
    connected = await skills[Calendar.CONNECT](
        req(other, Calendar.CONNECT, code="c", code_verifier="v"), ()
    )
    assert connected.data == {"status": "connected"}
    assert store.rows[(other, SERVICE)]["refresh_token"] == "refresh-1"
    bad = await skills[Calendar.CONNECT](
        req(other, Calendar.CONNECT, code="bad", code_verifier="v"), ()
    )
    assert bad.failed
    assert bad.output == "invalid_grant"
    await skills[Calendar.DISCONNECT](req(other, Calendar.DISCONNECT), ())
    assert (other, SERVICE) not in store.rows


async def test_list_respects_requested_max(env) -> None:
    skills, _, _, user = env
    result = await skills[Calendar.LIST](req(user, Calendar.LIST, day="2026-10-14", max=1), ())
    assert len(result.data["events"]) == 1


@pytest.mark.parametrize("limit", [0, -1, "2", True, 51])
async def test_list_rejects_invalid_max(env, limit) -> None:
    skills, _, _, user = env
    result = await skills[Calendar.LIST](req(user, Calendar.LIST, day="2026-10-14", max=limit), ())
    assert result.failed
    assert result.output == "invalid_params"


async def test_russian_stopwords_do_not_match_an_unrelated_event(env) -> None:
    skills, google, _, user = env
    google.events["ev-review"]["summary"] = "Встреча проекта"
    result = await skills[Calendar.PROPOSE](
        req(user, Calendar.PROPOSE, op="delete", title="удали встреча врача", day="2026-10-14"), ()
    )
    assert result.data["kind"] == "not_found"
