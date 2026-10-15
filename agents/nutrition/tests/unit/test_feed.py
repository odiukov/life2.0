from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from nutrition.application.feed import collect
from nutrition.application.ports import MealRepository
from nutrition.domain.meal import Macros, Meal, MealItem, MealType
from nutrition.testing import InMemoryMeals
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.feed import FeedSkill
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.profile import BodyProfileRepository
from shared.ports.users import UserSettingsRepository
from shared.skill_ids import Feed
from shared.testing.fakes import (
    FixedClock,
    InMemoryBodyProfiles,
    InMemoryHealthLogs,
    InMemoryUnitOfWorkFactory,
    InMemoryUserSettings,
)
from shared.testing.feed_contract import assert_feed_contract

LOCALES = Path(__file__).resolve().parents[4] / "packages" / "i18n" / "locales"
TR = JsonTranslator.from_dir(LOCALES)
KYIV = ZoneInfo("Europe/Kyiv")
NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
DAY = date(2026, 10, 14)
USER = uuid4()


async def run(*rows: HealthLogRow, day: date = DAY, locale: str = "en", meals_input=()) -> dict:
    logs, settings = InMemoryHealthLogs(), InMemoryUserSettings()
    settings.seed(USER, timezone="Europe/Kyiv", locale=locale)
    for row in rows:
        logs.seed(USER, row)
    meals, profile = InMemoryMeals(), InMemoryBodyProfiles()
    profile.rows[USER] = {"protein_goal_g": 100}
    for m in meals_input:
        await meals.add(USER, m)
    repos = {
        HealthLogRepository: logs,
        UserSettingsRepository: settings,
        MealRepository: meals,
        BodyProfileRepository: profile,
    }
    skill = FeedSkill(
        uow=InMemoryUnitOfWorkFactory(repos),
        clock=FixedClock(NOW),
        translator=TR,
        default_locale="en",
        collect=collect,
    )
    result = await skill(
        SkillRequest("t", "c", "", USER, Feed.EVENTS, None, False, {"date": day.isoformat()}), ()
    )
    assert not result.failed
    assert_feed_contract(result.data, day, KYIV)
    return result.data


async def run_meals(*meals):
    return await run(meals_input=meals)


def meal(
    at: datetime, kcal: float, protein: float, meal_type: MealType | None, source: str = "chat"
) -> Meal:
    return Meal.from_items(
        recorded_at=at,
        items=(MealItem("x", None, Macros(kcal=kcal, protein_g=protein)),),
        meal_type=meal_type,
        source=source,
    )


async def test_meals_of_the_day_with_types() -> None:
    lunch = datetime(2026, 10, 14, 9, 30, tzinfo=UTC)
    late = datetime(2026, 10, 14, 20, 30, tzinfo=UTC)  # 23:30 Kyiv: still today
    data = await run_meals(
        meal(lunch, 640.4, 32.2, MealType.LUNCH), meal(late, 180, 3, None, source="yazio")
    )
    events = [i for i in data["items"] if i["kind"] == "event"]
    assert [i["text"] for i in events] == [
        "Meal: 180 kcal, protein 3 g",
        "Lunch: 640 kcal, protein 32 g",
    ]
    assert events[-1]["id"] == f"nutrition:meal:chat:{lunch.isoformat()}"


async def test_actual_skill_caps_and_localizes_meals() -> None:
    data = await run(
        meals_input=[meal(NOW.replace(minute=n), 100, 2, MealType.LUNCH) for n in range(60)],
        locale="ru",
    )
    assert len(data["items"]) == 50
    assert all(i["text"] == "Обед: 100 ккал, белок 2 г" for i in data["items"])


async def test_russian_nonempty_insight() -> None:
    row = HealthLogRow("meal", NOW, {"totals": {"kcal": 200, "protein_g": 20}}, "chat", "nutrition")
    data = await run(row, locale="ru")
    assert [i["text"] for i in data["items"] if i["kind"] == "insight"] == [
        "Сегодня белка меньше цели на 80 г."
    ]
