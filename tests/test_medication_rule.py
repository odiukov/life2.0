from datetime import datetime, timedelta, timezone

from orchestrator.app.briefing_rules import medication_missed_rule


def _ts(days_ago: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


def test_silent_when_no_active_medications():
    metrics = {"medication": {"active": [], "logs": []}}
    assert medication_missed_rule(metrics) is None


def test_silent_when_taken_yesterday():
    metrics = {
        "medication": {
            "active": [{"name": "magnesium", "schedule": "daily 21:00"}],
            "logs": [{"name": "magnesium", "recorded_at": _ts(0)}],
        }
    }
    assert medication_missed_rule(metrics) is None


def test_fires_when_missed_2_days():
    metrics = {
        "medication": {
            "active": [{"name": "magnesium", "schedule": "daily 21:00"}],
            "logs": [{"name": "magnesium", "recorded_at": _ts(3)}],
        }
    }
    a = medication_missed_rule(metrics)
    assert a is not None
    assert a.rule_id == "medication.missed.2d"
    assert "magnesium" in a.message
    assert a.severity == "warn"
    assert a.category == "wellness"


def test_handles_multiple_misses_in_one_alert():
    metrics = {
        "medication": {
            "active": [
                {"name": "magnesium", "schedule": "daily 21:00"},
                {"name": "vitamin-d", "schedule": "daily morning"},
            ],
            "logs": [],  # both missed
        }
    }
    a = medication_missed_rule(metrics)
    assert a is not None
    assert "magnesium" in a.message and "vitamin-d" in a.message
