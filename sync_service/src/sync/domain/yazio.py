"""Yazio diary → one health_logs `meal` row per day and slot.

Yazio has no meal times, so each slot is placed at a fixed hour of the diary's day in the user's
zone (breakfast 08:00, lunch 12:00, snack 15:00, dinner 18:00). That keeps every meal on its own
local day and gives a stable dedup key.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo

from sync.domain.rows import Row

MealSlot = Literal["breakfast", "lunch", "dinner", "snack"]
SLOT_HOURS: Mapping[MealSlot, int] = {"breakfast": 8, "lunch": 12, "snack": 15, "dinner": 18}
Payload = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class YazioItem:
    slot: MealSlot
    name: str
    amount: float
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float


@dataclass(frozen=True, slots=True)
class YazioBundle:
    days: tuple[tuple[date, tuple[YazioItem, ...]], ...] = ()
    failures: tuple[str, ...] = ()


def _slot(entry: Payload) -> MealSlot:
    value = entry.get("daytime")
    return cast(MealSlot, value) if value in SLOT_HOURS else "snack"


def _num(value: object) -> float:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0


def _item(entry: Payload, name: str, amount: float, nutrients: Payload, factor: float) -> YazioItem:
    return YazioItem(
        slot=_slot(entry),
        name=name,
        amount=amount,
        kcal=factor * _num(nutrients.get("energy.energy")),
        protein_g=factor * _num(nutrients.get("nutrient.protein")),
        carbs_g=factor * _num(nutrients.get("nutrient.carb")),
        fat_g=factor * _num(nutrients.get("nutrient.fat")),
    )


def item_from_product(entry: Payload, product: Payload) -> YazioItem:
    """Product nutrients are per gram; `amount` is grams."""
    amount = _num(entry.get("amount"))
    return _item(
        entry, str(product.get("name") or ""), amount, product.get("nutrients") or {}, amount
    )


def item_from_simple(entry: Payload) -> YazioItem:
    """Simple products (free-form and AI-described meals) carry absolute nutrients for the portion."""
    amount = _num(entry.get("amount")) or _num(entry.get("serving_quantity")) or 1.0
    return _item(
        entry, str(entry.get("name") or "simple"), amount, entry.get("nutrients") or {}, 1.0
    )


def item_from_recipe(entry: Payload, recipe: Payload) -> YazioItem:
    """Recipe nutrients are per portion; the diary stores `portion_count`."""
    portions = _num(entry.get("portion_count")) or 1.0
    return _item(
        entry,
        str(recipe.get("name") or "recipe"),
        portions,
        recipe.get("nutrients") or {},
        portions,
    )


def _clean(value: float) -> float | int:
    return int(value) if value.is_integer() else value


def map_diary_day(day: date, items: Sequence[YazioItem], zone: ZoneInfo) -> list[Row]:
    by_slot: dict[MealSlot, list[YazioItem]] = {}
    for item in items:
        by_slot.setdefault(item.slot, []).append(item)
    rows: list[Row] = []
    for slot, slot_items in by_slot.items():
        totals = {"kcal": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
        listed = []
        for item in slot_items:
            listed.append(
                {
                    "name": item.name,
                    "amount_g": _clean(item.amount),
                    "kcal": _clean(item.kcal),
                    "protein_g": item.protein_g,
                    "carbs_g": item.carbs_g,
                    "fat_g": item.fat_g,
                }
            )
            totals["kcal"] += item.kcal
            totals["protein_g"] += item.protein_g
            totals["carbs_g"] += item.carbs_g
            totals["fat_g"] += item.fat_g
        when = datetime.combine(day, time(SLOT_HOURS[slot]), zone).astimezone(UTC)
        rows.append(
            Row(
                agent="nutrition",
                type="meal",
                source="yazio",
                recorded_at=when,
                data={
                    "meal_type": slot,
                    "items": listed,
                    "totals": totals,
                    "date": day.isoformat(),
                },
            )
        )
    return rows


def map_yazio(bundle: YazioBundle, zone: ZoneInfo) -> list[Row]:
    return [row for day, items in bundle.days for row in map_diary_day(day, items, zone)]
