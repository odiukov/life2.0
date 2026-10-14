"""What the LLM must return. Bounds reject obviously broken estimates."""

from __future__ import annotations

from datetime import time
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from shared.domain.energy import ActivityLevel, Sex

from nutrition.domain.meal import MealType

_LEGACY_ACTIVITY = {
    "lightly_active": "light",
    "moderately_active": "moderate",
    "extra_active": "very_active",
}


class ExtractedItem(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    amount_g: float | None = Field(default=None, ge=0, le=5000)
    kcal: float = Field(ge=0, le=5000)
    protein_g: float = Field(ge=0, le=500)
    carbs_g: float = Field(ge=0, le=1000)
    fat_g: float = Field(ge=0, le=500)


class MealExtraction(BaseModel):
    items: list[ExtractedItem] = Field(default_factory=list, max_length=30)
    meal_type: MealType | None = None
    eaten_at: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    confidence: Literal["high", "medium", "low"] = "medium"

    def eaten_time(self) -> time | None:
        return time.fromisoformat(self.eaten_at) if self.eaten_at else None


BodyProfileField = Literal["height_cm", "age", "sex", "activity_level", "calorie_goal_override"]


class BodyProfileExtraction(BaseModel):
    height_cm: float | None = Field(default=None, gt=50, lt=260)
    age: int | None = Field(default=None, gt=0, lt=120)
    sex: Sex | None = None
    activity_level: ActivityLevel | None = None
    calorie_goal_override: int | None = Field(default=None, ge=800, le=10000)
    cleared_fields: list[BodyProfileField] = Field(default_factory=list)

    @field_validator("activity_level", mode="before")
    @classmethod
    def _legacy_names(cls, value: object) -> object:
        if isinstance(value, str):
            return _LEGACY_ACTIVITY.get(value.strip().lower(), value.strip().lower())
        return value
