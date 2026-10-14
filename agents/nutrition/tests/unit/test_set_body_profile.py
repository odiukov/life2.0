from uuid import uuid4

from nutrition.application.set_body_profile import SetBodyProfile
from nutrition.testing import InMemoryBodyMetrics, InMemoryMeals, InMemoryProfiles, in_memory_uow
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.config import find_locales_dir
from shared.ports.llm import LLMUnavailable
from shared.testing.fakes import FakeLLM

TR = JsonTranslator.from_dir(find_locales_dir())


class World:
    def __init__(self) -> None:
        self.llm = FakeLLM()
        self.profiles = InMemoryProfiles()
        self.user = uuid4()
        self.profiles.seed(self.user, preferences={"body_profile": {"age": 30}})
        self.handler = SetBodyProfile(
            llm=self.llm,
            uow=in_memory_uow(InMemoryMeals(), self.profiles, InMemoryBodyMetrics()),
            translator=TR,
            default_locale="ru",
        )

    def request(self, text: str, params: dict[str, object] | None = None) -> SkillRequest:
        return SkillRequest(
            task_id="t",
            context_id="c",
            text=text,
            user_id=self.user,
            skill_id="set_body_profile",
            for_date=None,
            is_peer_call=False,
            params=params or {},
        )

    def body(self) -> dict[str, object]:
        return self.profiles.rows[self.user][1]["body_profile"]


async def test_saves_extracted_fields_and_lists_them() -> None:
    world = World()
    world.llm.queue_structured(
        {"height_cm": 180, "sex": "male", "activity_level": "moderately_active"}
    )
    result = await world.handler(world.request("рост 180, мужчина, умеренно активен"), ())
    assert world.body() == {
        "age": 30,
        "height_cm": 180.0,
        "sex": "male",
        "activity_level": "moderate",
    }
    assert result.output.startswith(
        "Профиль обновлён: рост 180 см, пол: мужской, активность: умеренная."
    )


async def test_explicit_params_override_the_extraction() -> None:
    world = World()
    world.llm.queue_structured({"age": 30})
    await world.handler(world.request("мне 30", {"age": 31}), ())
    assert world.body()["age"] == 31


async def test_nothing_found_changes_nothing() -> None:
    world = World()
    world.llm.queue_structured({})
    result = await world.handler(world.request("привет"), ())
    assert result.output.startswith("Не нашёл")
    assert world.body() == {"age": 30}


async def test_invalid_values_are_named_and_not_saved() -> None:
    world = World()
    world.llm.queue_structured({})
    result = await world.handler(world.request("мне 500", {"age": 500}), ())
    assert result.output == "Профиль не сохранён, проверь: возраст."
    assert world.body() == {"age": 30}


async def test_llm_failure_still_honors_explicit_params() -> None:
    world = World()
    world.llm.queue_structured(LLMUnavailable("down"))
    await world.handler(world.request("рост 170", {"height_cm": 170}), ())
    assert len(world.llm.calls) == 1
    assert world.body()["height_cm"] == 170.0


async def test_extracted_null_clears_only_the_stated_field() -> None:
    world = World()
    world.profiles.seed(world.user, preferences={"body_profile": {"age": 30, "height_cm": 180}})
    world.llm.queue_structured({"age": None})
    result = await world.handler(world.request("clear my age"), ())
    assert world.body() == {"height_cm": 180}
    assert result.output.startswith("Профиль обновлён: возраст: значение сброшено.")


async def test_explicit_null_overrides_extraction_and_confirms_all_clear() -> None:
    world = World()
    world.llm.queue_structured({"age": 31})
    result = await world.handler(world.request("clear my age", {"age": None}), ())
    assert world.body() == {}
    assert result.output.startswith("Профиль обновлён: возраст: значение сброшено.")
    assert result.log_entry is None


async def test_mixed_updates_and_clears_are_localized_and_omissions_preserved() -> None:
    world = World()
    world.profiles.seed(
        world.user, preferences={"locale": "en", "body_profile": {"age": 30, "sex": "male"}}
    )
    world.llm.queue_structured({"height_cm": 175, "age": None})
    result = await world.handler(world.request("height 175 and clear my age"), ())
    assert world.body() == {"sex": "male", "height_cm": 175.0}
    assert result.output.startswith("Profile updated: height 175 cm, age cleared.")
    assert "sex" not in result.output


async def test_params_only_update_skips_the_llm_and_ignores_unknown_keys() -> None:
    world = World()
    result = await world.handler(world.request("", {"height_cm": 170, "unexpected": 42}), ())
    assert world.llm.calls == []
    assert world.body() == {"age": 30, "height_cm": 170.0}
    assert result.output.startswith("Профиль обновлён: рост 170 см.")


async def test_invalid_extraction_leaves_profile_unchanged() -> None:
    world = World()
    world.llm.queue_structured({"age": 500})
    result = await world.handler(world.request("age 500"), ())
    assert world.body() == {"age": 30}
    assert result.output.startswith("Не нашёл")
