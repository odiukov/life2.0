from datetime import datetime, timezone

# Yazio meal_type int → string name + fixed hour for unique recorded_at per meal per day
_MEAL_TYPES = {
    0: ("breakfast", 8),
    1: ("lunch", 12),
    2: ("dinner", 18),
    3: ("snack", 15),
}


def map_diary_day(date_str: str, entries: list[dict]) -> list[dict]:
    """Map a list of Yazio diary entries for one day into health_logs row dicts.

    One row per meal_type. Multiple food items in the same meal are aggregated.
    """
    if not entries:
        return []

    # Group entries by meal_type
    by_meal: dict[int, list[dict]] = {}
    for entry in entries:
        mt = entry.get("meal_type", 3)
        by_meal.setdefault(mt, []).append(entry)

    rows = []
    for mt_int, meal_entries in by_meal.items():
        meal_name, hour = _MEAL_TYPES.get(mt_int, ("snack", 15))
        date_parts = [int(p) for p in date_str.split("-")]
        recorded_at = datetime(
            date_parts[0], date_parts[1], date_parts[2],
            hour, 0, 0, tzinfo=timezone.utc
        )

        items = []
        totals = {"kcal": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}

        for entry in meal_entries:
            food = entry.get("food", {})
            item = {
                "name": food.get("name", ""),
                "amount_g": food.get("amount", 0),
                "kcal": food.get("energy_kcal", 0),
                "protein_g": food.get("protein", 0),
                "carbs_g": food.get("carbohydrates", 0),
                "fat_g": food.get("fat", 0),
            }
            items.append(item)
            totals["kcal"] += item["kcal"]
            totals["protein_g"] += item["protein_g"]
            totals["carbs_g"] += item["carbs_g"]
            totals["fat_g"] += item["fat_g"]

        rows.append({
            "agent": "nutrition",
            "type": "meal",
            "source": "yazio",
            "recorded_at": recorded_at,
            "data": {
                "meal_type": meal_name,
                "items": items,
                "totals": totals,
                "date": date_str,
            },
        })

    return rows
