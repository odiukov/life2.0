"""Energy expenditure: activity levels, BMR, TDEE and the daily calorie goal."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite


class Sex(StrEnum):
    MALE = "male"
    FEMALE = "female"


class ActivityLevel(StrEnum):
    SEDENTARY = "sedentary"
    LIGHT = "light"
    MODERATE = "moderate"
    ACTIVE = "active"
    VERY_ACTIVE = "very_active"

    @property
    def multiplier(self) -> float:
        return _MULTIPLIERS[self]

    @classmethod
    def parse(cls, value: object, default: ActivityLevel | None = None) -> ActivityLevel:
        fallback = default or DEFAULT_ACTIVITY
        if not isinstance(value, str):
            return fallback
        key = value.strip().lower()
        if key in _ALIASES:
            return _ALIASES[key]
        try:
            return cls(key)
        except ValueError:
            return fallback


_MULTIPLIERS = {
    ActivityLevel.SEDENTARY: 1.2,
    ActivityLevel.LIGHT: 1.375,
    ActivityLevel.MODERATE: 1.55,
    ActivityLevel.ACTIVE: 1.725,
    ActivityLevel.VERY_ACTIVE: 1.9,
}
# Names used by older nutrition prompts and stored profiles.
_ALIASES = {
    "lightly_active": ActivityLevel.LIGHT,
    "moderately_active": ActivityLevel.MODERATE,
    "extra_active": ActivityLevel.VERY_ACTIVE,
}
DEFAULT_ACTIVITY = ActivityLevel.MODERATE


def _float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def _int(value: object) -> int | None:
    number = _float(value)
    return int(number) if number is not None else None


@dataclass(frozen=True, slots=True)
class BodyProfile:
    height_cm: float | None = None
    age: int | None = None
    sex: Sex | None = None
    activity_level: ActivityLevel | None = None
    calorie_goal_override: int | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> BodyProfile:
        sex = data.get("sex")
        activity = data.get("activity_level")
        return cls(
            height_cm=_float(data.get("height_cm")),
            age=_int(data.get("age")),
            sex=Sex(sex) if isinstance(sex, str) and sex in {s.value for s in Sex} else None,
            activity_level=ActivityLevel.parse(activity) if isinstance(activity, str) else None,
            calorie_goal_override=_int(data.get("calorie_goal_override")),
        )

    def to_mapping(self) -> dict[str, object]:
        values: dict[str, object | None] = {
            "height_cm": self.height_cm,
            "age": self.age,
            "sex": self.sex.value if self.sex else None,
            "activity_level": self.activity_level.value if self.activity_level else None,
            "calorie_goal_override": self.calorie_goal_override,
        }
        return {key: value for key, value in values.items() if value is not None}


def bmr_mifflin_st_jeor(*, weight_kg: float, height_cm: float, age: int, sex: Sex) -> float:
    return 10 * weight_kg + 6.25 * height_cm - 5 * age + (5 if sex is Sex.MALE else -161)


def tdee(bmr: float, activity: ActivityLevel) -> int:
    return round(bmr * activity.multiplier)


def calorie_goal(
    profile: BodyProfile, *, measured_bmr_kcal: float | None, weight_kg: float | None
) -> int | None:
    """Override, else measured BMR × activity, else Mifflin-St Jeor × activity, else unknown."""
    if profile.calorie_goal_override:
        return profile.calorie_goal_override
    activity = profile.activity_level or DEFAULT_ACTIVITY
    if measured_bmr_kcal:
        return tdee(measured_bmr_kcal, activity)
    if weight_kg and profile.height_cm and profile.age and profile.sex:
        bmr = bmr_mifflin_st_jeor(
            weight_kg=weight_kg, height_cm=profile.height_cm, age=profile.age, sex=profile.sex
        )
        return tdee(bmr, activity)
    return None
