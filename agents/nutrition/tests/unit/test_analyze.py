import asyncio
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from nutrition.application.analyze import AnalyzeNutrition
from nutrition.application.models import BodyComposition
from nutrition.application.prompts import AnalysisMode
from nutrition.domain.meal import CHAT_SOURCE, YAZIO_SOURCE, Macros, Meal, MealItem, MealType
from nutrition.testing import (
    FakeSync,
    InMemoryBodyMetrics,
    InMemoryMeals,
    InMemoryProfiles,
    in_memory_uow,
)
from shared.a2a.request import SkillRequest
from shared.adapters import peers as peer_adapter
from shared.adapters.i18n import JsonTranslator
from shared.config import find_locales_dir
from shared.grounding import GROUNDING_RULES
from shared.peer_chip_rules import PEER_CHIP_RULES
from shared.personas import IDENTITY
from shared.ports.llm import LLMTask, LLMUnavailable
from shared.testing.fakes import FakeLLM, FakePeerClient, FixedClock, InMemoryVectorMemory

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)  # 13:00 in Lisbon
TR = JsonTranslator.from_dir(find_locales_dir())


def meal(at: datetime, kcal: float, source: str) -> Meal:
    return Meal.from_items(
        recorded_at=at,
        items=(MealItem("еда", 100, Macros(kcal=kcal, protein_g=10, carbs_g=20, fat_g=5)),),
        meal_type=MealType.LUNCH,
        source=source,
    )


class World:
    def __init__(
        self,
        mode: AnalysisMode = "analyze_nutrition",
        peers: dict[str, str] | None = None,
        answer: object = "analysis text",
    ) -> None:
        self.mode = mode
        self.llm = FakeLLM()
        self.llm.queue_text(answer)
        self.meals, self.profiles, self.metrics = (
            InMemoryMeals(),
            InMemoryProfiles(),
            InMemoryBodyMetrics(),
        )
        self.peers = FakePeerClient(peers or {})
        self.memory = InMemoryVectorMemory()
        self.sync = FakeSync()
        self.user = uuid4()
        self.profiles.seed(self.user, timezone="Europe/Lisbon")
        self.handler = AnalyzeNutrition(
            mode=mode,
            llm=self.llm,
            uow=in_memory_uow(self.meals, self.profiles, self.metrics),
            clock=FixedClock(NOW),
            translator=TR,
            peers=self.peers,
            memory=self.memory,
            sync=self.sync,
            default_locale="ru",
        )

    def request(self, for_date: date | None = None) -> SkillRequest:
        return SkillRequest(
            task_id=str(uuid4()),
            context_id="c",
            text="как у меня с питанием?",
            user_id=self.user,
            skill_id=self.mode,
            for_date=for_date,
            is_peer_call=False,
            params={},
        )

    async def add(self, at: datetime, kcal: float, source: str = CHAT_SOURCE) -> None:
        await self.meals.add(self.user, meal(at, kcal, source))

    @property
    def prompt(self) -> str:
        call = self.llm.calls[0]
        return call.system + "\n" + call.user


async def test_intake_sums_chat_and_yazio_for_the_local_day_only() -> None:
    world = World()
    await world.add(datetime(2026, 10, 12, 22, 30, tzinfo=UTC), 999)  # 23:30 local, yesterday
    await world.add(datetime(2026, 10, 13, 7, 0, tzinfo=UTC), 300)
    await world.add(datetime(2026, 10, 13, 11, 0, tzinfo=UTC), 500, YAZIO_SOURCE)
    result = await world.handler(world.request(), ())
    assert result.output == "analysis text"
    assert "Eaten: 800 kcal" in world.prompt
    assert world.llm.calls[0].task is LLMTask.SMART


async def test_for_date_selects_that_local_day() -> None:
    world = World()
    await world.add(datetime(2026, 10, 12, 22, 30, tzinfo=UTC), 999)
    await world.handler(world.request(for_date=date(2026, 10, 12)), ())
    assert "Eaten: 999 kcal" in world.prompt
    assert "Day (2026-10-12)" in world.prompt


async def test_goal_unknown_without_profile_or_body_data() -> None:
    world = World()
    await world.handler(world.request(), ())
    assert "Goal: unknown" in world.prompt
    assert "goal unknown" in world.prompt


async def test_goal_and_remaining_from_profile_and_weight() -> None:
    world = World()
    world.profiles.seed(
        world.user,
        timezone="Europe/Lisbon",
        preferences={
            "body_profile": {
                "height_cm": 180,
                "age": 30,
                "sex": "male",
                "activity_level": "moderate",
            }
        },
    )
    world.metrics.seed(world.user, BodyComposition(NOW - timedelta(days=1), 80.0, 18.0, None))
    await world.add(datetime(2026, 10, 13, 7, 0, tzinfo=UTC), 800)
    await world.handler(world.request(), ())
    assert "Goal: 2759 kcal" in world.prompt
    assert "1959 kcal remaining" in world.prompt


async def test_only_answering_peers_are_used_and_reported() -> None:
    world = World(peers={"workout": "ran 5k yesterday"})
    result = await world.handler(world.request(for_date=date(2026, 10, 12)), ("workout", "sleep"))
    assert result.consulted == ("workout",)
    assert world.peers.calls[0]["wanted"] == {
        "workout": "analyze_workout",
        "sleep": "analyze_sleep",
    }
    assert world.peers.calls[0]["for_date"] == date(2026, 10, 12)
    assert "### workout\nran 5k yesterday" in world.prompt
    assert PEER_CHIP_RULES in world.prompt


async def test_no_consult_means_no_peer_call_and_no_chip_rules() -> None:
    world = World(peers={"workout": "unused"})
    result = await world.handler(world.request(), ())
    assert world.peers.calls == []
    assert result.consulted == ()
    assert PEER_CHIP_RULES not in world.prompt


async def test_prompt_has_identity_and_grounding_rules() -> None:
    world = World()
    await world.handler(world.request(), ())
    assert IDENTITY["nutrition"] in world.llm.calls[0].system
    assert GROUNDING_RULES in world.prompt


@pytest.mark.parametrize(
    ("mode", "tail"),
    [
        ("analyze_nutrition", "intake vs goal"),
        ("get_recommendations", "2–3 concrete nutrition actions"),
    ],
)
async def test_mode_selects_the_answer_shape(mode: AnalysisMode, tail: str) -> None:
    world = World(mode=mode)
    await world.handler(world.request(), ())
    assert tail in world.prompt


async def test_refreshes_sync_and_remembers_the_answer() -> None:
    world = World()
    await world.handler(world.request(), ())
    assert world.sync.calls == 1
    assert world.memory.items[0][3].text == "analysis text"


async def test_llm_down_answers_politely_and_remembers_nothing() -> None:
    world = World(answer=LLMUnavailable("down"))
    result = await world.handler(world.request(), ())
    assert result.output == TR.t("nutrition.errors.llm_unavailable", "ru")
    assert result.failed is True
    assert world.memory.items == []


async def test_local_day_uses_half_open_midnight_boundaries() -> None:
    world = World()
    await world.add(datetime(2026, 10, 12, 22, 59, 59, tzinfo=UTC), 999)
    await world.add(datetime(2026, 10, 12, 23, 0, tzinfo=UTC), 100)
    await world.add(datetime(2026, 10, 13, 22, 59, 59, tzinfo=UTC), 200, YAZIO_SOURCE)
    await world.add(datetime(2026, 10, 13, 23, 0, tzinfo=UTC), 888)
    await world.handler(world.request(), ())
    assert "Eaten: 300 kcal" in world.prompt


async def test_unknown_user_still_gets_analysis_without_a_goal() -> None:
    world = World()
    world.profiles.rows.clear()
    result = await world.handler(world.request(), ())
    assert result.output == "analysis text"
    assert "Goal: unknown" in world.prompt
    assert "No body composition measurements yet." in world.prompt


@pytest.mark.parametrize(
    ("preferences", "expected"),
    [
        ({}, 2480),
        ({"body_profile": {"calorie_goal_override": 2200}}, 2200),
    ],
)
async def test_measured_bmr_and_goal_override(preferences: dict, expected: int) -> None:
    world = World()
    world.profiles.seed(world.user, preferences=preferences)
    world.metrics.seed(world.user, BodyComposition(NOW, 80, 18, 1600))
    await world.handler(world.request(), ())
    assert f"Goal: {expected} kcal" in world.prompt


async def test_filters_blank_and_unrequested_peer_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    world = World()
    monkeypatch.setattr(
        world.peers,
        "fetch_artifacts",
        AsyncMock(
            return_value={
                "workout": " \n",
                "sleep": "slept well",
                "mood": "unrequested",
            }
        ),
    )
    result = await world.handler(world.request(), ("workout", "sleep", "unknown"))
    assert result.consulted == ("sleep",)
    assert "### sleep\nslept well" in world.prompt
    assert "### workout" not in world.prompt
    assert "unrequested" not in world.prompt


@pytest.mark.parametrize("failure", ["unavailable", "slow"])
async def test_adapter_peer_failures_allow_analysis(
    failure: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = World()
    if failure == "unavailable":
        fetch = AsyncMock(return_value={"workout": peer_adapter.LEGACY_UNAVAILABLE, "sleep": ""})
    else:

        async def wait_forever(*args: object, **kwargs: object) -> dict[str, str]:
            await asyncio.Event().wait()
            return {}

        fetch = AsyncMock(side_effect=wait_forever)
        monkeypatch.setattr(peer_adapter, "PEER_TIMEOUT_S", 0.01)
    monkeypatch.setattr(peer_adapter.legacy_peer, "fetch_peer_artifacts", fetch)
    world.handler._peers = peer_adapter.A2APeerClient(
        {"workout": "http://workout", "sleep": "http://sleep"}
    )
    result = await world.handler(world.request(), ("workout", "sleep"))
    assert result.output == "analysis text"
    assert result.consulted == ()
    assert "## Peer context" not in world.prompt
    assert PEER_CHIP_RULES not in world.prompt
    fetch.assert_awaited_once()


@pytest.mark.parametrize(
    ("port", "method"),
    [
        ("sync", "refresh"),
        ("peers", "fetch_artifacts"),
        ("memory", "search"),
        ("memory", "upsert"),
    ],
)
async def test_unexpected_best_effort_port_errors_do_not_block_analysis(
    port: str,
    method: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = World()
    monkeypatch.setattr(
        getattr(world, port), method, AsyncMock(side_effect=RuntimeError("backend down"))
    )
    result = await world.handler(world.request(), ("sleep",))
    assert result.output == "analysis text"
    assert result.consulted == ()


@pytest.mark.parametrize(
    ("port", "method"),
    [
        ("sync", "refresh"),
        ("peers", "fetch_artifacts"),
        ("memory", "search"),
        ("memory", "upsert"),
        ("llm", "text"),
    ],
)
async def test_cancellation_propagates_from_ports(
    port: str,
    method: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = World()
    monkeypatch.setattr(getattr(world, port), method, AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await world.handler(world.request(), ("sleep",))


async def test_memories_are_user_scoped_and_answer_is_stored_with_skill_metadata() -> None:
    world = World(mode="get_recommendations")
    await world.memory.upsert(
        user_id=world.user, agent="nutrition", key="old", text="existing advice", metadata={}
    )
    await world.memory.upsert(
        user_id=uuid4(), agent="nutrition", key="other", text="other user advice", metadata={}
    )
    request = world.request()
    await world.handler(request, ())
    assert "existing advice" in world.prompt
    assert "other user advice" not in world.prompt
    owner, agent, key, memory = world.memory.items[-1]
    assert (owner, agent, key) == (world.user, "nutrition", request.task_id)
    assert memory.metadata == {"skill": "get_recommendations"}


async def test_llm_failure_uses_profile_locale() -> None:
    world = World(answer=LLMUnavailable("down"))
    world.profiles.seed(world.user, preferences={"locale": "en"})
    result = await world.handler(world.request(), ())
    assert result.output == TR.t("nutrition.errors.llm_unavailable", "en")
    assert result.failed is True
    assert world.memory.items == []
