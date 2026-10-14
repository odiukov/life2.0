from collections import UserDict

import pytest
from shared.domain.energy import (
    DEFAULT_ACTIVITY,
    ActivityLevel,
    BodyProfile,
    Sex,
    bmr_mifflin_st_jeor,
    calorie_goal,
    tdee,
)


@pytest.mark.parametrize(
    ("weight", "height", "age", "sex", "expected"),
    [(80, 180, 30, Sex.MALE, 1780), (60, 165, 25, Sex.FEMALE, 1345.25)],
)
def test_mifflin_matches_the_orchestrator_formula(
    weight: float, height: float, age: int, sex: Sex, expected: float
) -> None:
    assert bmr_mifflin_st_jeor(weight_kg=weight, height_cm=height, age=age, sex=sex) == expected


@pytest.mark.parametrize(
    ("activity", "expected"),
    [
        (ActivityLevel.SEDENTARY, 1200),
        (ActivityLevel.LIGHT, 1375),
        (ActivityLevel.MODERATE, 1550),
        (ActivityLevel.ACTIVE, 1725),
        (ActivityLevel.VERY_ACTIVE, 1900),
    ],
)
def test_tdee_uses_the_level_multiplier(activity: ActivityLevel, expected: int) -> None:
    assert tdee(1000, activity) == expected


def test_tdee_rounds_to_integer_calories() -> None:
    assert tdee(1780, ActivityLevel.MODERATE) == 2759
    result = tdee(1345.25, ActivityLevel.LIGHT)
    assert result == 1850
    assert isinstance(result, int)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("sedentary", ActivityLevel.SEDENTARY),
        ("light", ActivityLevel.LIGHT),
        ("lightly_active", ActivityLevel.LIGHT),
        ("moderate", ActivityLevel.MODERATE),
        ("moderately_active", ActivityLevel.MODERATE),
        ("active", ActivityLevel.ACTIVE),
        ("very_active", ActivityLevel.VERY_ACTIVE),
        ("extra_active", ActivityLevel.VERY_ACTIVE),
        (" LIGHTLY_ACTIVE ", ActivityLevel.LIGHT),
        (ActivityLevel.ACTIVE, ActivityLevel.ACTIVE),
        ("unknown_level", ActivityLevel.MODERATE),
        (None, ActivityLevel.MODERATE),
        (123, ActivityLevel.MODERATE),
    ],
)
def test_parse_accepts_legacy_aliases_and_defaults(raw: object, expected: ActivityLevel) -> None:
    assert ActivityLevel.parse(raw) is expected


def test_parse_respects_an_explicit_fallback() -> None:
    assert ActivityLevel.parse({}, default=ActivityLevel.SEDENTARY) is ActivityLevel.SEDENTARY


def test_goal_precedence_override_then_measured_bmr_then_mifflin() -> None:
    full = BodyProfile(height_cm=180, age=30, sex=Sex.MALE, activity_level=ActivityLevel.MODERATE)
    assert (
        calorie_goal(BodyProfile(calorie_goal_override=2100), measured_bmr_kcal=1700, weight_kg=80)
        == 2100
    )
    assert calorie_goal(full, measured_bmr_kcal=1700, weight_kg=80) == 2635
    assert calorie_goal(full, measured_bmr_kcal=None, weight_kg=80) == 2759


def test_measured_bmr_needs_no_body_dimensions_and_defaults_activity() -> None:
    assert calorie_goal(BodyProfile(), measured_bmr_kcal=1700, weight_kg=None) == 2635
    assert (
        calorie_goal(
            BodyProfile(activity_level=ActivityLevel.LIGHT), measured_bmr_kcal=1700, weight_kg=None
        )
        == 2338
    )
    assert DEFAULT_ACTIVITY is ActivityLevel.MODERATE


@pytest.mark.parametrize(
    ("profile", "weight"),
    [
        (BodyProfile(), None),
        (BodyProfile(height_cm=180), 80),
        (BodyProfile(age=30, sex=Sex.MALE), 80),
        (BodyProfile(height_cm=180, sex=Sex.MALE), 80),
        (BodyProfile(height_cm=180, age=30), 80),
        (BodyProfile(height_cm=180, age=30, sex=Sex.MALE), None),
    ],
)
def test_goal_is_unknown_without_enough_data(profile: BodyProfile, weight: float | None) -> None:
    assert calorie_goal(profile, measured_bmr_kcal=None, weight_kg=weight) is None


def test_profile_mapping_round_trip_tolerates_junk() -> None:
    profile = BodyProfile.from_mapping(
        UserDict(
            {
                "height_cm": "181.5",
                "age": "30",
                "sex": "male",
                "activity_level": "moderately_active",
                "calorie_goal_override": None,
                "junk": 1,
            }
        )
    )
    assert profile == BodyProfile(
        height_cm=181.5, age=30, sex=Sex.MALE, activity_level=ActivityLevel.MODERATE
    )
    assert profile.to_mapping() == {
        "height_cm": 181.5,
        "age": 30,
        "sex": "male",
        "activity_level": "moderate",
    }
    assert BodyProfile.from_mapping({"sex": "robot", "age": "old"}) == BodyProfile()


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        True,
        False,
        "junk",
        [],
        {},
        float("nan"),
        float("inf"),
        float("-inf"),
        "nan",
        "inf",
        "-inf",
        10**1000,
    ],
)
def test_invalid_numeric_fields_are_ignored(invalid: object) -> None:
    assert (
        BodyProfile.from_mapping(
            {"height_cm": invalid, "age": invalid, "calorie_goal_override": invalid}
        )
        == BodyProfile()
    )


def test_profile_mapping_preserves_override_and_normalizes_activity() -> None:
    profile = BodyProfile.from_mapping(
        {"calorie_goal_override": "2100", "sex": "female", "activity_level": "nonsense"}
    )
    assert profile.to_mapping() == {
        "calorie_goal_override": 2100,
        "sex": "female",
        "activity_level": "moderate",
    }
    assert BodyProfile.from_mapping({}).to_mapping() == {}
    assert BodyProfile.from_mapping({"activity_level": 4}).activity_level is None
