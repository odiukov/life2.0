from datetime import datetime, timezone
from sync_service.app.yazio_mapper import map_diary_day

DIARY_ENTRIES = [
    {
        "meal_type": 0,  # breakfast
        "food": {
            "name": "Oatmeal",
            "amount": 80,
            "energy_kcal": 296,
            "protein": 10.4,
            "carbohydrates": 48.0,
            "fat": 5.6,
        },
    },
    {
        "meal_type": 1,  # lunch
        "food": {
            "name": "Chicken breast",
            "amount": 200,
            "energy_kcal": 220,
            "protein": 41.0,
            "carbohydrates": 0.0,
            "fat": 4.8,
        },
    },
    {
        "meal_type": 1,  # lunch — second item same meal
        "food": {
            "name": "Rice",
            "amount": 150,
            "energy_kcal": 195,
            "protein": 3.6,
            "carbohydrates": 43.5,
            "fat": 0.3,
        },
    },
]


def test_map_diary_day_returns_one_row_per_meal_type():
    rows = map_diary_day("2026-04-12", DIARY_ENTRIES)
    meal_types = [r["data"]["meal_type"] for r in rows]
    assert "breakfast" in meal_types
    assert "lunch" in meal_types
    assert len(rows) == 2  # 1 breakfast + 1 lunch


def test_map_diary_day_breakfast_row_schema():
    rows = map_diary_day("2026-04-12", DIARY_ENTRIES)
    breakfast = next(r for r in rows if r["data"]["meal_type"] == "breakfast")
    assert breakfast["agent"] == "nutrition"
    assert breakfast["type"] == "meal"
    assert breakfast["source"] == "yazio"
    assert isinstance(breakfast["recorded_at"], datetime)
    assert breakfast["recorded_at"].tzinfo is not None
    assert breakfast["data"]["date"] == "2026-04-12"
    assert len(breakfast["data"]["items"]) == 1
    item = breakfast["data"]["items"][0]
    assert item["name"] == "Oatmeal"
    assert item["amount_g"] == 80
    assert item["kcal"] == 296
    assert item["protein_g"] == 10.4
    assert item["carbs_g"] == 48.0
    assert item["fat_g"] == 5.6


def test_map_diary_day_lunch_aggregates_items():
    rows = map_diary_day("2026-04-12", DIARY_ENTRIES)
    lunch = next(r for r in rows if r["data"]["meal_type"] == "lunch")
    assert len(lunch["data"]["items"]) == 2
    totals = lunch["data"]["totals"]
    assert totals["kcal"] == 220 + 195
    assert round(totals["protein_g"], 1) == round(41.0 + 3.6, 1)
    assert round(totals["carbs_g"], 1) == round(0.0 + 43.5, 1)
    assert round(totals["fat_g"], 1) == round(4.8 + 0.3, 1)


def test_map_diary_day_unique_recorded_at_per_meal():
    rows = map_diary_day("2026-04-12", DIARY_ENTRIES)
    timestamps = [r["recorded_at"] for r in rows]
    assert len(timestamps) == len(set(timestamps))


def test_map_diary_day_empty_entries_returns_empty():
    assert map_diary_day("2026-04-12", []) == []


def test_map_diary_day_unknown_meal_type_maps_to_snack():
    entries = [{"meal_type": 99, "food": {"name": "X", "amount": 10,
                "energy_kcal": 50, "protein": 1, "carbohydrates": 5, "fat": 1}}]
    rows = map_diary_day("2026-04-12", entries)
    assert rows[0]["data"]["meal_type"] == "snack"
