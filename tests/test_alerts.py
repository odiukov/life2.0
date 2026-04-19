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
    assert a.throttle_hours == 12  # default


def test_alert_immutable():
    a = Alert(rule_id="x", severity="info", message="m", category="wellness")
    try:
        a.severity = "crit"
        assert False, "Alert should be frozen"
    except Exception:
        pass


def test_alert_severity_validates():
    try:
        Alert(rule_id="x", severity="panic", message="m", category="wellness")
        assert False
    except ValueError:
        pass


def test_alert_category_validates():
    try:
        Alert(rule_id="x", severity="warn", message="m", category="random")
        assert False
    except ValueError:
        pass
