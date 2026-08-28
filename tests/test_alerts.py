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


def test_alert_back_compat_explicit_message_still_works():
    a = Alert(
        rule_id="custom.rule",
        severity="warn",
        message="explicit string",
        category="wellness",
    )
    assert a.message == "explicit string"


def test_alert_rejects_when_neither_message_nor_key_given():
    import pytest
    with pytest.raises(ValueError, match="message"):
        Alert(rule_id="x", severity="warn", category="wellness")


def test_alert_title_auto_derived_when_empty():
    a = Alert(rule_id="sleep.no_data.1d", severity="info", message="m", category="wellness")
    assert a.title == "Sleep"


def test_alert_explicit_title_preserved():
    a = Alert(
        rule_id="sleep.no_data.1d", severity="info", message="m",
        category="wellness", title="Custom Title",
    )
    assert a.title == "Custom Title"
