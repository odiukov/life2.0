import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import _compute_tdee


def test_male_moderate():
    # 80kg, 180cm, 30yo, male, moderate → BMR=1780, TDEE=2759
    result = _compute_tdee(80, 180, 30, "male", "moderate")
    assert result == 2759


def test_female_light():
    # 60kg, 165cm, 25yo, female, light → BMR=1345.25, TDEE=1850
    result = _compute_tdee(60, 165, 25, "female", "light")
    assert result == 1850


def test_unknown_activity_defaults_to_moderate():
    r1 = _compute_tdee(70, 175, 28, "male", "moderate")
    r2 = _compute_tdee(70, 175, 28, "male", "unknown_level")
    assert r1 == r2


def test_returns_int():
    result = _compute_tdee(75, 175, 27, "male", "active")
    assert isinstance(result, int)
