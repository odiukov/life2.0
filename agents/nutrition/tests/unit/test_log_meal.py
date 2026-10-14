import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from nutrition.application.log_meal import LogMeal
from nutrition.domain.meal import CHAT_SOURCE, Meal
from nutrition.testing import InMemoryBodyMetrics, InMemoryMeals, InMemoryProfiles, in_memory_uow
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.config import find_locales_dir
from shared.ports.llm import LLMInvalidOutput, LLMUnavailable
from shared.testing.fakes import FakeLLM, FixedClock, InMemoryVectorMemory

NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
TR = JsonTranslator.from_dir(find_locales_dir())

OMELETTE_AND_TOAST = {
    "items": [
        {"name": "омлет", "amount_g": 180, "kcal": 300, "protein_g": 20, "carbs_g": 2, "fat_g": 22},
        {"name": "тост", "amount_g": 30, "kcal": 120, "protein_g": 7, "carbs_g": 16, "fat_g": 4},
    ],
    "meal_type": "breakfast",
    "confidence": "high",
}


class World:
    def __init__(self, now: datetime = NOW) -> None:
        self.llm = FakeLLM()
        self.meals, self.profiles, self.metrics = (
            InMemoryMeals(),
            InMemoryProfiles(),
            InMemoryBodyMetrics(),
        )
        self.memory = InMemoryVectorMemory()
        self.user = uuid4()
        self.profiles.seed(self.user, timezone="Europe/Lisbon")
        self.handler = LogMeal(
            llm=self.llm,
            uow=in_memory_uow(self.meals, self.profiles, self.metrics),
            clock=FixedClock(now),
            translator=TR,
            memory=self.memory,
            default_locale="ru",
        )

    def request(self, text: str) -> SkillRequest:
        return SkillRequest(
            task_id=str(uuid4()),
            context_id="c",
            text=text,
            user_id=self.user,
            skill_id="log_meal",
            for_date=None,
            is_peer_call=False,
            params={},
        )

    def stored(self, user: UUID | None = None):
        return self.meals.rows.get(user or self.user, [])


async def test_logs_the_meal_and_confirms_from_the_catalog() -> None:
    world = World()
    world.llm.queue_structured(OMELETTE_AND_TOAST)
    result = await world.handler(world.request("съел омлет из 3 яиц и тост"), ())
    assert result.output == "Записал: омлет (180 г), тост (30 г) — 420 ккал · Б 27 / Ж 26 / У 18"
    assert result.log_entry == "съел омлет из 3 яиц и тост"
    [meal] = world.stored()
    assert meal.source == CHAT_SOURCE
    assert meal.recorded_at == NOW
    assert result.log_recorded_at == NOW
    assert world.memory.items
    assert world.memory.items[0][3].text == result.output


async def test_prompt_carries_local_time_and_message() -> None:
    world = World()
    world.llm.queue_structured(OMELETTE_AND_TOAST)
    await world.handler(world.request("съел омлет"), ())
    call = world.llm.calls[0]
    assert "2026-10-13 10:00" in call.user  # 09:00 UTC is 10:00 in Lisbon
    assert "съел омлет" in call.user


async def test_low_confidence_adds_a_hint() -> None:
    world = World()
    world.llm.queue_structured({**OMELETTE_AND_TOAST, "confidence": "low"})
    result = await world.handler(world.request("что-то съел"), ())
    assert result.output.endswith("Оценка примерная — поправь, если знаешь точнее.")


@pytest.mark.parametrize("answer", [{"items": []}, LLMInvalidOutput("x", "bad")])
async def test_not_food_writes_nothing(answer: object) -> None:
    world = World()
    world.llm.queue_structured(answer)
    result = await world.handler(world.request("привет"), ())
    assert result.output.startswith("Не понял")
    assert result.failed is isinstance(answer, LLMInvalidOutput)
    assert result.log_entry is None
    assert world.stored() == []


async def test_llm_down_is_reported_politely() -> None:
    world = World()
    world.llm.queue_structured(LLMUnavailable("down"))
    result = await world.handler(world.request("съел суп"), ())
    assert result.output == TR.t("nutrition.errors.llm_unavailable", "ru")
    assert result.failed is True
    assert world.stored() == []


async def test_stated_time_after_now_means_yesterday() -> None:
    world = World(now=datetime(2026, 10, 12, 23, 30, tzinfo=UTC))  # 00:30 local, 13 Oct
    world.llm.queue_structured({**OMELETTE_AND_TOAST, "eaten_at": "23:00"})
    await world.handler(world.request("поужинал в 23:00"), ())
    assert world.stored()[0].recorded_at == datetime(2026, 10, 12, 22, 0, tzinfo=UTC)


async def test_two_meals_at_the_same_stated_time_are_both_kept() -> None:
    world = World()
    world.llm.queue_structured(
        {**OMELETTE_AND_TOAST, "eaten_at": "08:00"}, {**OMELETTE_AND_TOAST, "eaten_at": "08:00"}
    )
    await world.handler(world.request("в 8:00 омлет"), ())
    await world.handler(world.request("в 8:00 ещё тост"), ())
    times = [m.recorded_at for m in world.stored()]
    assert times[1] - times[0] == timedelta(microseconds=1)
    assert sum(m.totals.kcal for m in world.stored()) == 840


async def test_user_locale_wins_over_default() -> None:
    world = World()
    world.profiles.seed(world.user, timezone="UTC", preferences={"locale": "en"})
    world.llm.queue_structured(OMELETTE_AND_TOAST)
    result = await world.handler(world.request("omelette and toast"), ())
    assert result.output.startswith("Logged: омлет (180 g)")


async def test_commit_finishes_before_memory_and_log_entry_result() -> None:
    world = World()
    factory = in_memory_uow(world.meals, world.profiles, world.metrics)
    observed: list[tuple[int, int]] = []

    class CommitCheckingMemory(InMemoryVectorMemory):
        async def upsert(self, **kwargs: object) -> None:
            observed.append((len(factory.commits), len(world.stored())))
            raise RuntimeError("unexpected memory backend failure")

    world.handler = LogMeal(
        llm=world.llm,
        uow=factory,
        clock=FixedClock(NOW),
        translator=TR,
        memory=CommitCheckingMemory(),
        default_locale="ru",
    )
    world.llm.queue_structured(OMELETTE_AND_TOAST)
    result = await world.handler(world.request("omelette and toast"), ())
    assert result.log_entry == "omelette and toast"
    assert result.log_recorded_at == world.stored()[0].recorded_at
    assert observed == [(2, 1)]
    assert factory.commits == [world.user, world.user]
    assert factory.rollbacks == []


async def test_persistence_failure_does_not_write_memory_or_confirm_a_meal() -> None:
    world = World()

    class FailingMeals(InMemoryMeals):
        async def add(self, user_id: UUID, meal: Meal) -> Meal:
            raise RuntimeError("meal write failed")

    world.handler = LogMeal(
        llm=world.llm,
        uow=in_memory_uow(FailingMeals(), world.profiles, world.metrics),
        clock=FixedClock(NOW),
        translator=TR,
        memory=world.memory,
        default_locale="ru",
    )
    world.llm.queue_structured(OMELETTE_AND_TOAST)
    with pytest.raises(RuntimeError, match="meal write failed"):
        await world.handler(world.request("omelette and toast"), ())
    assert world.memory.items == []


@pytest.mark.parametrize("zone", [None, "", "Mars/Olympus"])
async def test_missing_or_invalid_zone_logs_at_utc(zone: str | None) -> None:
    world = World()
    world.profiles.seed(world.user, timezone=zone)
    world.llm.queue_structured(OMELETTE_AND_TOAST)
    result = await world.handler(world.request("omelette and toast"), ())
    assert result.log_recorded_at == NOW
    assert "2026-10-13 09:00 (UTC)" in world.llm.calls[0].user


async def test_commit_failure_prevents_memory_and_success_result() -> None:
    world = World()
    factory = in_memory_uow(world.meals, world.profiles, world.metrics)

    class CommitFailingFactory:
        def __init__(self) -> None:
            self.calls = 0

        @asynccontextmanager
        async def for_user(self, user_id: UUID):
            self.calls += 1
            async with factory.for_user(user_id) as uow:
                yield uow
                if self.calls == 2:
                    raise RuntimeError("commit failed")

    world.handler = LogMeal(
        llm=world.llm,
        uow=CommitFailingFactory(),
        clock=FixedClock(NOW),
        translator=TR,
        memory=world.memory,
        default_locale="ru",
    )
    world.llm.queue_structured(OMELETTE_AND_TOAST)
    with pytest.raises(RuntimeError, match="commit failed"):
        await world.handler(world.request("omelette and toast"), ())
    assert world.memory.items == []
    assert factory.rollbacks == [world.user]


async def test_memory_cancellation_propagates_after_commit() -> None:
    world = World()

    class CancelledMemory(InMemoryVectorMemory):
        async def upsert(self, **kwargs: object) -> None:
            raise asyncio.CancelledError

    world.handler = LogMeal(
        llm=world.llm,
        uow=in_memory_uow(world.meals, world.profiles, world.metrics),
        clock=FixedClock(NOW),
        translator=TR,
        memory=CancelledMemory(),
        default_locale="ru",
    )
    world.llm.queue_structured(OMELETTE_AND_TOAST)
    with pytest.raises(asyncio.CancelledError):
        await world.handler(world.request("omelette and toast"), ())
    assert len(world.stored()) == 1
