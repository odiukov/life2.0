"""Meals and their aggregate energy and macronutrients."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

CHAT_SOURCE = "chat"
YAZIO_SOURCE = "yazio"


class MealType(StrEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


@dataclass(frozen=True, slots=True)
class Macros:
    kcal: float = 0.0
    protein_g: float = 0.0
    carbs_g: float = 0.0
    fat_g: float = 0.0

    def __add__(self, other: Macros) -> Macros:
        return Macros(
            kcal=self.kcal + other.kcal,
            protein_g=self.protein_g + other.protein_g,
            carbs_g=self.carbs_g + other.carbs_g,
            fat_g=self.fat_g + other.fat_g,
        )


@dataclass(frozen=True, slots=True)
class MealItem:
    name: str
    amount_g: float | None
    macros: Macros


@dataclass(frozen=True, slots=True)
class Meal:
    recorded_at: datetime
    items: tuple[MealItem, ...]
    totals: Macros
    meal_type: MealType | None
    source: str

    def __post_init__(self) -> None:
        if self.recorded_at.utcoffset() is None:
            raise ValueError("Meal.recorded_at must be timezone-aware")

    @classmethod
    def from_items(
        cls,
        *,
        recorded_at: datetime,
        items: tuple[MealItem, ...],
        meal_type: MealType | None,
        source: str,
    ) -> Meal:
        totals = sum((item.macros for item in items), Macros())
        return cls(
            recorded_at=recorded_at, items=items, totals=totals, meal_type=meal_type, source=source
        )

    def with_recorded_at(self, when: datetime) -> Meal:
        return replace(self, recorded_at=when)


def total_intake(meals: Iterable[Meal]) -> Macros:
    return sum((meal.totals for meal in meals), Macros())
