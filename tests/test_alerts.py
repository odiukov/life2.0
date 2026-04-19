import dataclasses

import pytest

from orchestrator.app.alerts import Alert


def test_alert_has_required_fields():
    a = Alert(
        rule_id="medication.missed.2d",
        severity="warn",
        message="skipped magnesium for 2 days",
        category="wellness",
    )
    assert a.rule_id == "medication.missed.2d"
    assert a.severity == "warn"
    assert a.category == "wellness"
    assert a.throttle_hours == 12


def test_alert_immutable():
    a = Alert(rule_id="x", severity="info", message="m", category="wellness")
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.severity = "crit"


def test_alert_severity_validates():
    with pytest.raises(ValueError, match="severity"):
        Alert(rule_id="x", severity="panic", message="m", category="wellness")


def test_alert_category_validates():
    with pytest.raises(ValueError, match="category"):
        Alert(rule_id="x", severity="warn", message="m", category="random")
