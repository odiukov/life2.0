import pytest
from orchestrator.app.main import _hrv_pct, _mood_pct, _steps_pct


# _hrv_pct
def test_hrv_pct_at_baseline():
    assert _hrv_pct(50, 50.0) == 100

def test_hrv_pct_below_baseline():
    assert _hrv_pct(40, 80.0) == 50

def test_hrv_pct_clamped_above_100():
    assert _hrv_pct(200, 50.0) == 100

def test_hrv_pct_none_hrv():
    assert _hrv_pct(None, 50.0) is None

def test_hrv_pct_none_baseline():
    assert _hrv_pct(50, None) is None

def test_hrv_pct_zero_baseline():
    assert _hrv_pct(50, 0.0) is None


# _mood_pct
def test_mood_pct_typical():
    assert _mood_pct(7.0) == 70

def test_mood_pct_max():
    assert _mood_pct(10.0) == 100

def test_mood_pct_none():
    assert _mood_pct(None) is None

def test_mood_pct_clamped():
    assert _mood_pct(11.0) == 100


# _steps_pct
def test_steps_pct_typical():
    assert _steps_pct(8000) == 80

def test_steps_pct_over_goal():
    assert _steps_pct(15000) == 100

def test_steps_pct_none():
    assert _steps_pct(None) is None

def test_steps_pct_zero():
    assert _steps_pct(0) == 0
