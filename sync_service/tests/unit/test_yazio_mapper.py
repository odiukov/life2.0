from datetime import UTC, date, datetime

import pytest
from sync.domain.yazio import (
    YazioBundle,
    YazioItem,
    item_from_product,
    item_from_recipe,
    item_from_simple,
    map_diary_day,
    map_yazio,
)
from sync_fixtures import (
    LISBON,
    NEW_YORK,
    YAZIO_PRODUCT,
    YAZIO_PRODUCT_ENTRY,
    YAZIO_RECIPE,
    YAZIO_RECIPE_ENTRY,
    YAZIO_SIMPLE_ENTRY,
)

DAY = date(2026, 10, 13)


def test_product_nutrients_are_per_gram() -> None:
    item = item_from_product(YAZIO_PRODUCT_ENTRY, YAZIO_PRODUCT)
    assert item.slot == "breakfast"
    assert item.name == "Oatmeal"
    assert item.amount == 80
    assert item.kcal == pytest.approx(296)
    assert item.protein_g == pytest.approx(10.4)
    assert item.carbs_g == pytest.approx(48)
    assert item.fat_g == pytest.approx(5.6)


def test_simple_products_are_absolute_and_keep_cyrillic_names() -> None:
    item = item_from_simple(YAZIO_SIMPLE_ENTRY)
    assert (item.slot, item.name, item.amount, item.kcal, item.protein_g) == (
        "lunch",
        "Борщ (AI)",
        1,
        368,
        27,
    )
    bare = item_from_simple({"daytime": "snack"})
    assert (bare.name, bare.amount, bare.kcal) == ("simple", 1, 0.0)


def test_recipes_multiply_per_portion_and_default_to_one() -> None:
    item = item_from_recipe(YAZIO_RECIPE_ENTRY, YAZIO_RECIPE)
    assert (item.slot, item.amount, item.kcal, item.fat_g) == ("dinner", 2, 900, 40)
    assert item_from_recipe({"recipe_id": "r", "daytime": "dinner"}, YAZIO_RECIPE).kcal == 450


def test_unknown_daytime_is_a_snack() -> None:
    assert item_from_simple({"daytime": "midnight"}).slot == "snack"
    assert item_from_simple({}).slot == "snack"


def test_one_row_per_slot_with_items_and_totals() -> None:
    items = [
        YazioItem("lunch", "Chicken breast", 200, 220, 41.0, 0.0, 4.8),
        YazioItem("lunch", "Rice", 150, 195, 3.6, 43.5, 0.3),
        YazioItem("breakfast", "Oatmeal", 80, 296, 10.4, 48.0, 5.6),
    ]
    rows = {r.data["meal_type"]: r for r in map_diary_day(DAY, items, LISBON)}
    assert set(rows) == {"breakfast", "lunch"}
    lunch = rows["lunch"]
    assert (lunch.agent, lunch.type, lunch.source) == ("nutrition", "meal", "yazio")
    assert lunch.data["date"] == "2026-10-13"
    assert lunch.data["items"] == [
        {
            "name": "Chicken breast",
            "amount_g": 200,
            "kcal": 220,
            "protein_g": 41.0,
            "carbs_g": 0.0,
            "fat_g": 4.8,
        },
        {
            "name": "Rice",
            "amount_g": 150,
            "kcal": 195,
            "protein_g": 3.6,
            "carbs_g": 43.5,
            "fat_g": 0.3,
        },
    ]
    assert lunch.data["totals"] == pytest.approx(
        {"kcal": 415, "protein_g": 44.6, "carbs_g": 43.5, "fat_g": 5.1}
    )
    assert map_diary_day(DAY, [], LISBON) == []


def test_yazio_slots_use_the_users_zone() -> None:
    items = [
        YazioItem(slot, slot, 1, 1, 0, 0, 0) for slot in ("breakfast", "lunch", "snack", "dinner")
    ]
    ny = {r.data["meal_type"]: r.recorded_at for r in map_diary_day(DAY, items, NEW_YORK)}
    assert ny == {
        "breakfast": datetime(2026, 10, 13, 12, 0, tzinfo=UTC),  # 08:00 EDT
        "lunch": datetime(2026, 10, 13, 16, 0, tzinfo=UTC),
        "snack": datetime(2026, 10, 13, 19, 0, tzinfo=UTC),
        "dinner": datetime(2026, 10, 13, 22, 0, tzinfo=UTC),
    }
    for when in ny.values():  # every slot stays on the diary's own local day
        assert when.astimezone(NEW_YORK).date() == DAY


def test_bundle_maps_every_day() -> None:
    bundle = YazioBundle(
        days=((DAY, (YazioItem("dinner", "x", 1, 500, 1, 1, 1),)), (date(2026, 10, 12), ())),
        failures=("product p-1",),
    )
    rows = map_yazio(bundle, LISBON)
    assert [(r.data["date"], r.data["meal_type"]) for r in rows] == [("2026-10-13", "dinner")]
