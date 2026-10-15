from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from orchestrator.adapters.langgraph.tools import build_tools
from orchestrator.application.ports import PeerReply, PeerUnavailable, RunContext
from orchestrator.testing import FakeHealthSync, FakePeerAgents, RecordedProposals
from shared.a2a.proposals import Proposal, to_data
from shared.ports.skills import SkillCallError, SkillReply
from shared.testing.fakes import FakeSkillClient

CTX = RunContext(
    uuid4(),
    uuid4(),
    None,
    None,
    ZoneInfo("Europe/Kyiv"),
    "ru",
    datetime(2026, 10, 14, 6, 30, tzinfo=UTC),
)


def tools(
    peers: FakePeerAgents, calendar: FakeSkillClient | None = None, text: str = "привет", sync=None
):  # type: ignore[no-untyped-def]
    recorder = RecordedProposals()
    built = build_tools(
        CTX,
        last_user_text=text,
        peers=peers,
        skills=lambda agent: calendar or FakeSkillClient(lambda *a: SkillReply("", {})),
        proposals=recorder,
        sync=sync or FakeHealthSync(),
    )
    return {t.name: t for t in built}, recorder


def call(tool, **args):  # type: ignore[no-untyped-def]
    return tool.ainvoke({"type": "tool_call", "id": "c1", "name": tool.name, "args": args})


async def test_one_ask_tool_per_conversational_agent_with_its_skills() -> None:
    named, _ = tools(FakePeerAgents())
    assert {n for n in named if n.startswith("ask_")} == {
        "ask_sleep_agent",
        "ask_workout_agent",
        "ask_nutrition_agent",
        "ask_kitchen_agent",
        "ask_body_agent",
        "ask_mood_agent",
        "ask_habits_agent",
        "ask_recovery_agent",
        "ask_medication_agent",
        "ask_finance_agent",
        "ask_home_agent",
    }
    assert {"calendar_list", "calendar_propose", "sync_health_data"} <= set(named)
    schema = named["ask_kitchen_agent"].args_schema.model_json_schema()  # type: ignore[union-attr]
    assert set(schema["properties"]["skill"]["enum"]) == {
        "kitchen.update_inventory",
        "kitchen.query",
    }
    assert "focus_sources" in named["ask_sleep_agent"].args
    assert "focus_sources" not in named["ask_mood_agent"].args
    assert "verbatim" in named["ask_kitchen_agent"].description


async def test_ask_passes_skill_text_and_reports_consulted_peers() -> None:
    peers = FakePeerAgents({"sleep": PeerReply("sleep summary", consulted=("nutrition",))})
    named, _ = tools(peers)
    message = await call(
        named["ask_sleep_agent"], message="how did I sleep?", skill="analyze_sleep"
    )
    assert message.content == "sleep summary"
    assert message.artifact == {"agent": "sleep", "consulted": ["nutrition"]}
    assert peers.calls == [("sleep", CTX.user_id, "analyze_sleep", "how did I sleep?", None)]


async def test_focus_sources_are_autodetected_from_the_users_words() -> None:
    peers = FakePeerAgents({"workout": PeerReply("plan")})
    named, _ = tools(peers, text="посоветуй тренировку на основе сна и питания")
    await call(
        named["ask_workout_agent"], message="тренировка?", skill="get_workout_recommendations"
    )
    assert peers.calls[0][4] == ["sleep", "nutrition"]


async def test_an_unavailable_agent_is_reported_to_the_model_not_raised() -> None:
    named, _ = tools(FakePeerAgents({"mood": PeerUnavailable()}))
    message = await call(named["ask_mood_agent"], message="как я?", skill="analyze_mood")
    assert "unavailable" in message.content.lower()
    assert message.artifact["failed"] is True


async def test_home_proposals_are_recorded_and_hidden_from_the_model() -> None:
    proposal = Proposal(
        "home.call_tool",
        "Выключить: Lamp?",
        {
            "tool": "HassTurnOff",
            "args": {"name": "Lamp"},
            "household_id": str(uuid4()),
            "credentials_version": 1,
        },
    )
    named, recorder = tools(
        FakePeerAgents({"home": PeerReply("Выключу после подтверждения.", data=to_data(proposal))})
    )
    message = await call(named["ask_home_agent"], message="выключи лампу", skill="home.ask")
    assert recorder.recorded == [("home", proposal)]
    assert message.artifact["proposal_id"] == str(recorder.actions[0].id)
    assert "confirm" in message.content.lower()
    assert "HassTurnOff" not in message.content


async def test_proposals_from_agents_that_cannot_propose_are_ignored() -> None:
    proposal = Proposal("home.call_tool", "x", {"tool": "HassTurnOff"})
    named, recorder = tools(FakePeerAgents({"kitchen": PeerReply("ok", data=to_data(proposal))}))
    await call(named["ask_kitchen_agent"], message="молоко", skill="kitchen.update_inventory")
    assert recorder.recorded == []


async def test_calendar_list_and_propose() -> None:
    def responder(skill, user, params, text):  # type: ignore[no-untyped-def]
        if skill == "calendar.list":
            return SkillReply(
                "Calendar events for 2026-10-14:\n• 19:00-20:00: Gym (event_id: ev-gym)",
                {"events": []},
            )
        if params.get("title") == "gym":
            return SkillReply(
                "",
                {
                    "kind": "ambiguous",
                    "candidates": [
                        {"id": "a", "summary": "Gym"},
                        {"id": "b", "summary": "Gym with Ana"},
                    ],
                },
            )
        return SkillReply(
            "",
            to_data(
                Proposal(
                    "calendar.delete",
                    "Удалить «Gym»?",
                    {"op": "delete", "event_id": "ev-gym", "etag": '"1"', "fields": {}},
                )
            ),
        )

    named, recorder = tools(FakePeerAgents(), calendar=FakeSkillClient(responder))
    listed = await call(named["calendar_list"], day="2026-10-14")
    assert "Gym" in listed.content
    assert listed.artifact["agent"] == "calendar"
    ambiguous = await call(named["calendar_propose"], op="delete", title="gym", day="2026-10-14")
    assert "Gym with Ana" in ambiguous.content
    assert recorder.recorded == []
    await call(named["calendar_propose"], op="delete", event_id="ev-gym")
    assert recorder.recorded[0][0] == "calendar"


@pytest.mark.parametrize(
    ("code", "phrase"),
    [("not_connected", "not connected"), ("calendar_unavailable", "unavailable")],
)
async def test_calendar_failures_are_plain_sentences(code: str, phrase: str) -> None:
    named, _ = tools(FakePeerAgents(), calendar=FakeSkillClient(lambda *a: SkillCallError(code)))
    message = await call(named["calendar_list"], day="2026-10-14")
    assert phrase in message.content.lower()
    assert code not in message.content


async def test_sync_tool_reports_per_service_without_provider_text() -> None:
    sync = FakeHealthSync(
        [
            {"service": "garmin", "status": "ok", "written": 3},
            {"service": "yazio", "status": "auth_failed", "written": 0},
            {"service": "x", "status": "not_connected", "written": 0},
        ]
    )
    named, _ = tools(FakePeerAgents(), sync=sync)
    message = await call(named["sync_health_data"])
    assert (
        message.content
        == "Sync: garmin ok (3 new or updated); yazio auth_failed — reconnect it in Integrations."
    )
    assert sync.users == [CTX.user_id]


@pytest.mark.parametrize(
    ("agent", "action"), [("home", "calendar.delete"), ("calendar", "home.call_tool")]
)
async def test_proposal_action_must_belong_to_responding_agent(agent: str, action: str) -> None:
    data = to_data(Proposal(action, "Change?", {"private": "not model input"}))
    named, recorder = tools(
        FakePeerAgents({"home": PeerReply("ready", data=data)}),
        calendar=FakeSkillClient(lambda *a: SkillReply("", data)),
    )
    if agent == "home":
        message = await call(named["ask_home_agent"], message="change", skill="home.ask")
    else:
        message = await call(named["calendar_propose"], op="delete", event_id="event")
    assert recorder.recorded == []
    assert message.artifact["failed"] is True
    assert "private" not in message.content


async def test_failed_peer_cannot_record_a_proposal() -> None:
    named, recorder = tools(
        FakePeerAgents(
            {
                "home": PeerReply(
                    "failed", data=to_data(Proposal("home.call_tool", "Change?", {})), failed=True
                )
            }
        )
    )
    message = await call(named["ask_home_agent"], message="change", skill="home.ask")
    assert recorder.recorded == []
    assert message.artifact["failed"] is True


async def test_tool_schemas_exclude_run_context_and_apply_skills() -> None:
    named, _ = tools(FakePeerAgents())
    for tool in named.values():
        assert (
            not {"user_id", "task_id", "household_id", "locale", "timezone", "lead_agent"}
            & tool.args.keys()
        )
    assert all("apply" not in name for name in named)
    assert named["ask_home_agent"].args["skill"].get("const") == "home.ask"


def test_all_tool_skill_choices_match_the_catalog() -> None:
    from orchestrator.domain.catalog import CATALOG, tool_name

    named, _ = tools(FakePeerAgents())
    for name, entry in CATALOG.items():
        if entry.tool == "ask":
            field = named[tool_name(name)].args["skill"]
            assert tuple(field.get("enum", [field.get("const")])) == entry.skills


async def test_kitchen_question_is_returned_verbatim_with_call_id() -> None:
    reply = "Which shelf should I use?"
    named, _ = tools(FakePeerAgents({"kitchen": PeerReply(reply)}))
    message = await call(
        named["ask_kitchen_agent"], message="milk", skill="kitchen.update_inventory"
    )
    assert message.content == reply
    assert message.tool_call_id == "c1"


@pytest.mark.parametrize(
    ("down", "expected"),
    [
        (True, "Sync failed: the sync service is unavailable."),
        (False, "Sync: no integrations connected."),
    ],
)
async def test_sync_failure_and_empty_results(down, expected) -> None:
    named, _ = tools(FakePeerAgents(), sync=FakeHealthSync(down=down))
    message = await call(named["sync_health_data"])
    assert message.content == expected
