"""Pins nutrition's analysis prompts byte for byte; the pipeline refactor must not change them."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from nutrition.application.analyze import AnalyzeNutrition
from nutrition.application.models import BodyComposition
from nutrition.domain.meal import CHAT_SOURCE, YAZIO_SOURCE, Macros, Meal, MealItem, MealType
from nutrition.testing import (
    FakeSync,
    InMemoryBodyMetrics,
    InMemoryMeals,
    InMemoryProfiles,
    in_memory_uow,
)
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.config import find_locales_dir
from shared.testing.fakes import FakeLLM, FakePeerClient, FixedClock, InMemoryVectorMemory

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
USER = UUID(int=42)


def meal(at: datetime, kcal: float, source: str, name: str) -> Meal:
    return Meal.from_items(
        recorded_at=at,
        items=(MealItem(name, 150, Macros(kcal=kcal, protein_g=20, carbs_g=30, fat_g=10)),),
        meal_type=MealType.LUNCH,
        source=source,
    )


@pytest.mark.parametrize("mode", ["analyze_nutrition", "get_recommendations"])
@pytest.mark.parametrize("with_peers", [False, True])
async def test_prompt_snapshot(mode: str, with_peers: bool, snapshot) -> None:  # type: ignore[no-untyped-def]
    meals, profiles, metrics = InMemoryMeals(), InMemoryProfiles(), InMemoryBodyMetrics()
    profiles.seed(
        USER,
        timezone="Europe/Lisbon",
        preferences={
            "locale": "ru",
            "body_profile": {
                "height_cm": 180,
                "age": 30,
                "sex": "male",
                "activity_level": "moderate",
            },
        },
    )
    await meals.add(USER, meal(NOW - timedelta(hours=3), 520, CHAT_SOURCE, "омлет"))
    await meals.add(USER, meal(NOW - timedelta(days=1), 700, YAZIO_SOURCE, "паста"))
    metrics.seed(
        USER,
        BodyComposition(
            recorded_at=NOW - timedelta(days=2), weight_kg=82.5, body_fat_pct=18.2, bmr_kcal=1800
        ),
    )
    memory = InMemoryVectorMemory()
    await memory.upsert(
        user_id=USER, agent="nutrition", key="m1", text="eats late on Fridays", metadata={}
    )
    llm = FakeLLM()
    llm.queue_text("ok")
    handler = AnalyzeNutrition(
        mode=mode,  # type: ignore[arg-type]
        llm=llm,
        uow=in_memory_uow(meals, profiles, metrics),
        clock=FixedClock(NOW),
        translator=JsonTranslator.from_dir(find_locales_dir()),
        peers=FakePeerClient({"workout": "ran 10k yesterday", "sleep": "6h"} if with_peers else {}),
        memory=memory,
        sync=FakeSync(),
        default_locale="ru",
    )
    request = SkillRequest(
        task_id="t",
        context_id="c",
        text="как я питаюсь?",
        user_id=USER,
        skill_id=mode,
        for_date=None,
        is_peer_call=False,
    )
    await handler(request, ("workout", "sleep") if with_peers else ())
    call = llm.calls[0]
    snapshot(
        f"{mode}{'-peers' if with_peers else ''}", f"{call.system}\n===== USER =====\n{call.user}\n"
    )
