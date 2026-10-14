import json
from uuid import uuid4

import httpx
import pytest
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from nutrition.application.set_body_profile import SetBodyProfile
from nutrition.testing import InMemoryBodyMetrics, InMemoryMeals, InMemoryProfiles, in_memory_uow
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.adapters.llm.langchain_provider import LangChainLLMProvider
from shared.config import find_locales_dir
from shared.ports.llm import LLMTask, LLMUnavailable
from shared.testing.fakes import FakeLLM

TR = JsonTranslator.from_dir(find_locales_dir())


@pytest.mark.parametrize("clear_age", [False, True])
async def test_strict_provider_partial_update_preserves_unmentioned_fields(clear_age: bool) -> None:
    world = World()
    initial = {
        "height_cm": 180,
        "age": 30,
        "sex": "male",
        "activity_level": "moderate",
        "calorie_goal_override": 2500,
    }
    world.profiles.seed(world.user, preferences={"body_profile": initial})
    captured: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        answer = {
            "height_cm": None,
            "age": None if clear_age else 31,
            "sex": None,
            "activity_level": None,
            "calorie_goal_override": None,
            "cleared_fields": ["age"] if clear_age else [],
        }
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-synthetic",
                "object": "chat.completion",
                "created": 1,
                "model": "synthetic",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(answer)},
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:

        class Factory:
            def chat_model(self, task: LLMTask) -> BaseChatModel:
                return ChatOpenAI(
                    model="synthetic",
                    api_key="synthetic-no-network",
                    http_async_client=client,
                    max_retries=0,
                )

        handler = SetBodyProfile(
            llm=LangChainLLMProvider(Factory(), timeout_s=5),
            uow=in_memory_uow(InMemoryMeals(), world.profiles, InMemoryBodyMetrics()),
            translator=TR,
            default_locale="en",
        )
        await handler(world.request("clear my age" if clear_age else "I am now 31 years old"), ())
    expected = {k: v for k, v in initial.items() if k != "age"}
    if not clear_age:
        expected["age"] = 31
    assert world.body() == expected
    schema = captured[0]["response_format"]["json_schema"]
    assert schema["strict"] is True
    assert set(schema["schema"]["required"]) == {*initial, "cleared_fields"}


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
    world.llm.queue_structured({"age": None, "cleared_fields": ["age"]})
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
    world.llm.queue_structured({"height_cm": 175, "age": None, "cleared_fields": ["age"]})
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
