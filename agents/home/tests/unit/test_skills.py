from datetime import UTC, datetime
from uuid import uuid4

import pytest
from home.application.skills import build_skills
from home.domain.actions import ToolCall
from home.testing import FakeHomeAgent, FakeHomeAssistant
from shared.a2a.proposals import from_data
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.config import find_locales_dir
from shared.ports.household_credentials import HouseholdCredentialStore
from shared.ports.users import UserSettingsRepository
from shared.skill_ids import Home
from shared.testing.fakes import (
    FixedClock,
    InMemoryHouseholdCredentials,
    InMemoryUnitOfWorkFactory,
    InMemoryUserSettings,
)

NOW = datetime(2026, 10, 14, 18, tzinfo=UTC)
TR = JsonTranslator.from_dir(find_locales_dir())


def env(agent: FakeHomeAgent | None = None, ask_timeout_s: float = 5.0):
    creds, settings = InMemoryHouseholdCredentials(), InMemoryUserSettings()
    uow = InMemoryUnitOfWorkFactory(
        {HouseholdCredentialStore: creds, UserSettingsRepository: settings}
    )
    assistant, agent = FakeHomeAssistant(), agent or FakeHomeAgent()
    skills = build_skills(
        uow=uow,
        assistant=assistant,
        agent=agent,
        clock=FixedClock(NOW),
        translator=TR,
        default_locale="ru",
        ask_timeout_s=ask_timeout_s,
    )
    house = uuid4()
    ana, bo = uuid4(), uuid4()
    creds.seed_member(ana, house, "Ana")
    creds.seed_member(bo, house, "Bo")
    return skills, creds, assistant, agent, house, ana, bo


def req(user, skill, text: str = "", **params) -> SkillRequest:
    return SkillRequest("t", "c", text, user, skill, None, False, params=params)


async def connect(skills, user) -> None:
    result = await skills[Home.CONNECT](
        req(user, Home.CONNECT, base_url="http://ha.local:8123", token="secret-token"), ()
    )
    assert result.data == {"status": "connected", "version": 1}


async def test_one_connection_for_the_whole_household() -> None:
    skills, _creds, *_, ana, bo = env()
    await connect(skills, ana)
    status = await skills[Home.STATUS](req(bo, Home.STATUS), ())
    assert status.data is not None
    assert (status.data["connected"], status.data["connected_by"]) == (True, "Ana")
    assert isinstance(status.data["connected_at"], str)


async def test_connect_validates_the_token_and_url() -> None:
    skills, *_, ana, _ = env()
    wrong = await skills[Home.CONNECT](
        req(ana, Home.CONNECT, base_url="http://ha.local:8123", token="wrong"), ()
    )
    assert wrong.failed
    assert wrong.output == "invalid_token"
    bad = await skills[Home.CONNECT](
        req(ana, Home.CONNECT, base_url="ftp://x", token="tttttttt"), ()
    )
    assert bad.failed
    assert bad.output == "invalid_params"


async def test_mutations_come_back_as_proposals() -> None:
    call = ToolCall("HassTurnOff", {"name": "Living room lamp", "area": "Living room"})
    skills, _creds, assistant, _agent, house, ana, _ = env(
        FakeHomeAgent("Confirm turning off the lamp.", call)
    )
    await connect(skills, ana)
    result = await skills[Home.ASK](req(ana, Home.ASK, "выключи лампу в гостиной"), ())
    proposal = from_data(result.data)
    assert proposal is not None
    assert proposal.action == "home.call_tool"
    assert proposal.payload == {
        "tool": "HassTurnOff",
        "args": dict(call.args),
        "household_id": str(house),
        "credentials_version": 1,
    }
    assert "Living room lamp" in proposal.summary
    assert assistant.calls == []  # nothing ran


async def test_reads_answer_without_a_proposal() -> None:
    skills, *_, ana, _ = env(FakeHomeAgent("The bedroom is 21 °C."))
    await connect(skills, ana)
    result = await skills[Home.ASK](req(ana, Home.ASK, "сколько градусов в спальне"), ())
    assert result.output == "The bedroom is 21 °C."
    assert result.data is None


async def test_unreachable_home_assistant_answers_with_a_code() -> None:
    skills, *_, ana, _ = env(FakeHomeAgent(hang=True), ask_timeout_s=0.05)
    await connect(skills, ana)
    result = await skills[Home.ASK](req(ana, Home.ASK, "что дома?"), ())
    assert result.failed
    assert result.output == "home_unavailable"


async def test_apply_runs_the_confirmed_call_once_versions_match() -> None:
    call = ToolCall("HassTurnOff", {"name": "Lamp"})
    skills, _creds, assistant, _agent, _house, ana, bo = env(FakeHomeAgent("ok", call))
    await connect(skills, ana)
    proposal = from_data((await skills[Home.ASK](req(ana, Home.ASK, "off"), ())).data)
    applied = await skills[Home.APPLY](req(bo, Home.APPLY, payload=dict(proposal.payload)), ())
    assert applied.data == {"status": "applied"}
    assert assistant.calls == [("HassTurnOff", {"name": "Lamp"})]


async def test_apply_refuses_a_changed_connection() -> None:
    call = ToolCall("HassTurnOff", {"name": "Lamp"})
    skills, _creds, assistant, _agent, _house, ana, bo = env(FakeHomeAgent("ok", call))
    await connect(skills, ana)
    proposal = from_data((await skills[Home.ASK](req(ana, Home.ASK, "off"), ())).data)
    await skills[Home.CONNECT](
        req(bo, Home.CONNECT, base_url="http://ha.local:8123", token="new-token"), ()
    )
    result = await skills[Home.APPLY](req(ana, Home.APPLY, payload=dict(proposal.payload)), ())
    assert result.failed
    assert result.output == "connection_changed"
    assert assistant.calls == []


async def test_member_who_left_cannot_apply_a_home_action() -> None:
    call = ToolCall("HassTurnOn", {"name": "Heater"})
    skills, creds, assistant, _agent, _house, ana, bo = env(FakeHomeAgent("ok", call))
    await connect(skills, ana)
    proposal = from_data((await skills[Home.ASK](req(bo, Home.ASK, "on"), ())).data)
    creds.seed_member(bo, uuid4(), "Bo")  # Bo left: leaving gives a new household of one
    result = await skills[Home.APPLY](req(bo, Home.APPLY, payload=dict(proposal.payload)), ())
    assert result.failed
    assert result.output == "household_changed"
    assert assistant.calls == []


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"tool": "GetLiveContext", "args": {}, "household_id": "x", "credentials_version": 1},
        {"tool": "HassTurnOn", "args": [], "household_id": "x", "credentials_version": 1},
    ],
)
async def test_apply_rejects_malformed_or_read_only_payloads(payload) -> None:
    skills, *_, ana, _ = env()
    await connect(skills, ana)
    result = await skills[Home.APPLY](req(ana, Home.APPLY, payload=payload), ())
    assert result.failed
    assert result.output == "invalid_params"


async def test_no_connection_and_no_household() -> None:
    skills, *_, ana, _ = env()
    missing = await skills[Home.ASK](req(ana, Home.ASK, "что дома"), ())
    assert missing.failed
    assert missing.output == "not_connected"
    stranger = await skills[Home.CONNECT](
        req(uuid4(), Home.CONNECT, base_url="http://ha:8123", token="tttttttt"), ()
    )
    assert stranger.failed
    assert stranger.output == "no_household"


async def test_reconnecting_invalidates_old_proposals() -> None:
    skills, _creds, assistant, _agent, _house, ana, _ = env(
        FakeHomeAgent("Confirm", ToolCall("HassTurnOff", {"name": "Lamp"}))
    )
    await connect(skills, ana)
    proposal = from_data((await skills[Home.ASK](req(ana, Home.ASK, "off"), ())).data)
    assert proposal is not None
    await skills[Home.DISCONNECT](req(ana, Home.DISCONNECT), ())
    await skills[Home.CONNECT](
        req(ana, Home.CONNECT, base_url="http://other", token="new-token"), ()
    )
    result = await skills[Home.APPLY](req(ana, Home.APPLY, payload=dict(proposal.payload)), ())
    assert result.failed
    assert result.output == "connection_changed"
    assert assistant.calls == []


@pytest.mark.parametrize(
    "url", ["http://[", "http://ha:bad", "http://user:secret@ha", "http://ha/path?token=x"]
)
async def test_connect_rejects_malformed_base_urls(url) -> None:
    skills, *_, ana, _ = env()
    result = await skills[Home.CONNECT](req(ana, Home.CONNECT, base_url=url, token="token"), ())
    assert result.failed
    assert result.output == "invalid_params"


async def test_apply_rejects_boolean_generation() -> None:
    skills, _creds, assistant, _agent, house, ana, _ = env()
    await connect(skills, ana)
    result = await skills[Home.APPLY](
        req(
            ana,
            Home.APPLY,
            payload={
                "tool": "HassTurnOff",
                "args": {},
                "household_id": str(house),
                "credentials_version": True,
            },
        ),
        (),
    )
    assert result.failed
    assert result.output == "invalid_params"
    assert assistant.calls == []
