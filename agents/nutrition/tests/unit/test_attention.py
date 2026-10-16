from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from nutrition.application.attention import collect
from nutrition.application.ports import MealRepository
from nutrition.domain.meal import Macros, Meal, MealItem, MealType
from nutrition.testing import InMemoryMeals
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.attention import AttentionSkill
from shared.ports.health_logs import HealthLogRepository
from shared.ports.profile import BodyProfileRepository
from shared.ports.users import UserSettingsRepository
from shared.skill_ids import Attention
from shared.testing.attention_contract import assert_attention_contract
from shared.testing.fakes import (
    FixedClock,
    InMemoryBodyProfiles,
    InMemoryHealthLogs,
    InMemoryUnitOfWorkFactory,
    InMemoryUserSettings,
)

TR = JsonTranslator.from_dir(Path(__file__).resolve().parents[4] / "packages" / "i18n" / "locales")
AFTERNOON = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)  # 15:00 Kyiv
MORNING = datetime(2026, 10, 16, 6, 0, tzinfo=UTC)
USER = uuid4()
FULL = {"height_cm": 180, "age": 40, "sex": "male", "activity_level": "moderate", "weight_kg": 80}


def lunch() -> Meal:
    return Meal.from_items(
        recorded_at=AFTERNOON,
        items=(MealItem("x", None, Macros(kcal=500, protein_g=30)),),
        meal_type=MealType.LUNCH,
        source="chat",
    )


async def run(
    profile: dict[str, object], meals: list[Meal] | None = None, now: datetime = AFTERNOON
) -> list[dict[str, object]]:
    settings, profiles, store = InMemoryUserSettings(), InMemoryBodyProfiles(), InMemoryMeals()
    settings.seed(USER, timezone="Europe/Kyiv")
    await profiles.update(USER, profile)
    for meal in meals or []:
        await store.add(USER, meal)
    skill = AttentionSkill(
        uow=InMemoryUnitOfWorkFactory(
            {
                UserSettingsRepository: settings,
                BodyProfileRepository: profiles,
                MealRepository: store,
                HealthLogRepository: InMemoryHealthLogs(),
            }
        ),
        clock=FixedClock(now),
        translator=TR,
        default_locale="en",
        collect=collect,
    )
    result = await skill(SkillRequest("t", "c", "", USER, Attention.ITEMS, None, False, {}), ())
    assert_attention_contract(result.data)
    return result.data["items"]  # type: ignore[index, return-value]


async def test_missing_profile_and_no_meals() -> None:
    items = await run({})
    assert [(i["id"], i["level"], i["action"]["type"]) for i in items] == [  # type: ignore[index]
        ("nutrition:profile", "high", "profile"),
        ("nutrition:meals:2026-10-16", "normal", "task"),
    ]
    assert items[1]["action"]["prompt"] == "Log my meal:"  # type: ignore[index]


async def test_full_profile_and_a_meal_give_nothing() -> None:
    assert await run(FULL, [lunch()]) == []


async def test_meals_item_waits_until_two_pm() -> None:
    assert await run(FULL, now=MORNING) == []
