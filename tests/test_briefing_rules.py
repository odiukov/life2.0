from datetime import datetime, timedelta, timezone

from orchestrator.app.alerts import Alert
from orchestrator.app.briefing_rules import (
    collect_alerts,
    sleep_missing_data_rule,
)


def test_sleep_missing_data_fires_when_no_sleep_rows():
    metrics = {"sleep": None}
    alert = sleep_missing_data_rule(metrics)
    assert isinstance(alert, Alert)
    assert alert.rule_id == "sleep.no_data.1d"
    assert alert.severity == "info"
    assert alert.category == "wellness"


def test_sleep_missing_data_silent_when_data_present():
    metrics = {"sleep": {"duration_seconds": 25200, "deep_sleep_seconds": 5400}}
    alert = sleep_missing_data_rule(metrics)
    assert alert is None


def test_collect_alerts_aggregates_all_non_none():
    metrics = {"sleep": None}
    alerts = collect_alerts(metrics)
    assert len(alerts) == 1
    assert alerts[0].rule_id == "sleep.no_data.1d"


def test_collect_alerts_empty_when_everything_ok():
    metrics = {"sleep": {"duration_seconds": 25200}}
    alerts = collect_alerts(metrics)
    assert alerts == []


def _body_metrics(latest: dict | None, history: list[dict]) -> dict:
    if latest is None:
        return {"body": None}
    return {"body": {"latest": latest, "recent_90d": [latest, *history]}}


def test_body_weight_gain_fires_at_exactly_1_5_kg():
    from orchestrator.app.briefing_rules import body_weight_gain_rule
    now = datetime.now(timezone.utc)
    latest = {"weight_kg": 82.0, "body_fat_pct": None,
              "lean_mass_kg": None, "bmi": None, "recorded_at": now}
    ref = {"weight_kg": 80.5, "body_fat_pct": None,
           "lean_mass_kg": None, "bmi": None, "recorded_at": now - timedelta(days=7)}
    alert = body_weight_gain_rule(_body_metrics(latest, [ref]))
    assert alert is not None
    assert alert.rule_id == "body.weight_gain.7d"
    assert alert.severity == "warn"
    assert alert.category == "wellness"
    assert alert.throttle_hours == 24
    assert "80.5" in alert.message and "82.0" in alert.message
    assert "+1.5" in alert.message


def test_body_weight_gain_fires_at_typical_delta():
    from orchestrator.app.briefing_rules import body_weight_gain_rule
    now = datetime.now(timezone.utc)
    latest = {"weight_kg": 83.0, "body_fat_pct": None,
              "lean_mass_kg": None, "bmi": None, "recorded_at": now}
    ref = {"weight_kg": 80.7, "body_fat_pct": None,
           "lean_mass_kg": None, "bmi": None, "recorded_at": now - timedelta(days=6, hours=12)}
    alert = body_weight_gain_rule(_body_metrics(latest, [ref]))
    assert alert is not None
    assert alert.rule_id == "body.weight_gain.7d"


def test_body_weight_gain_silent_below_threshold():
    from orchestrator.app.briefing_rules import body_weight_gain_rule
    now = datetime.now(timezone.utc)
    latest = {"weight_kg": 81.4, "body_fat_pct": None,
              "lean_mass_kg": None, "bmi": None, "recorded_at": now}
    ref = {"weight_kg": 80.5, "body_fat_pct": None,
           "lean_mass_kg": None, "bmi": None, "recorded_at": now - timedelta(days=7)}
    assert body_weight_gain_rule(_body_metrics(latest, [ref])) is None


def test_body_weight_gain_silent_when_no_reference_in_window():
    from orchestrator.app.briefing_rules import body_weight_gain_rule
    now = datetime.now(timezone.utc)
    latest = {"weight_kg": 82.0, "body_fat_pct": None,
              "lean_mass_kg": None, "bmi": None, "recorded_at": now}
    # nearest historical weight is 3 days old — outside 5-9d window
    ref = {"weight_kg": 80.5, "body_fat_pct": None,
           "lean_mass_kg": None, "bmi": None, "recorded_at": now - timedelta(days=3)}
    assert body_weight_gain_rule(_body_metrics(latest, [ref])) is None


def test_body_weight_gain_silent_when_no_body():
    from orchestrator.app.briefing_rules import body_weight_gain_rule
    assert body_weight_gain_rule({"body": None}) is None
    now = datetime.now(timezone.utc)
    latest = {"weight_kg": None, "body_fat_pct": None,
              "lean_mass_kg": None, "bmi": None, "recorded_at": now}
    assert body_weight_gain_rule(_body_metrics(latest, [])) is None
