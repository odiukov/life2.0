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


def test_body_weight_gain_picks_closest_candidate_in_window():
    """Two candidates in ±2d window at different distances from the 7-day
    mark — rule must pick the closer one (d=0) so delta=+1.0 kg is below
    threshold and NO alert fires. If the farther one (d=2d) wins instead,
    delta=+3.0 kg and the rule would wrongly fire."""
    from orchestrator.app.briefing_rules import body_weight_gain_rule
    now = datetime.now(timezone.utc)
    latest = {"weight_kg": 82.0, "body_fat_pct": None,
              "lean_mass_kg": None, "bmi": None, "recorded_at": now}
    near = {"weight_kg": 81.0, "body_fat_pct": None,
            "lean_mass_kg": None, "bmi": None,
            "recorded_at": now - timedelta(days=7)}
    far = {"weight_kg": 79.0, "body_fat_pct": None,
           "lean_mass_kg": None, "bmi": None,
           "recorded_at": now - timedelta(days=5)}
    # Pass `far` first so the loop has to prefer `near` by distance, not by
    # list position.
    assert body_weight_gain_rule(_body_metrics(latest, [far, near])) is None


def test_body_fat_high_fires_at_p90_boundary():
    from orchestrator.app.briefing_rules import body_fat_high_rule
    now = datetime.now(timezone.utc)
    # 10 points; statistics.quantiles(n=10) returns 9 cut-points; index 8 = p90.
    # For sample [14..23] step 1: Python 3.13 exclusive method gives p90 = 22.9.
    # Set latest = 22.9 to hit boundary.
    fats = [14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0, 21.0, 22.0, 23.0]
    rows = []
    for i, v in enumerate(fats):
        rows.append({"weight_kg": None, "body_fat_pct": v,
                     "lean_mass_kg": None, "bmi": None,
                     "recorded_at": now - timedelta(days=i)})
    latest = {"weight_kg": None, "body_fat_pct": 22.9,
              "lean_mass_kg": None, "bmi": None, "recorded_at": now}
    metrics = {"body": {"latest": latest, "recent_90d": [latest, *rows]}}
    alert = body_fat_high_rule(metrics)
    assert alert is not None
    assert alert.rule_id == "body.fat_pct_high.90d"
    assert alert.severity == "warn"
    assert alert.throttle_hours == 168
    assert "22.9" in alert.message


def test_body_fat_high_silent_when_fewer_than_10_points():
    from orchestrator.app.briefing_rules import body_fat_high_rule
    now = datetime.now(timezone.utc)
    fats = [18.0] * 9  # only 9 points
    rows = [{"weight_kg": None, "body_fat_pct": v,
             "lean_mass_kg": None, "bmi": None,
             "recorded_at": now - timedelta(days=i)} for i, v in enumerate(fats)]
    latest = {"weight_kg": None, "body_fat_pct": 25.0,
              "lean_mass_kg": None, "bmi": None, "recorded_at": now}
    metrics = {"body": {"latest": latest, "recent_90d": [latest, *rows]}}
    assert body_fat_high_rule(metrics) is None


def test_body_fat_high_silent_when_below_p90():
    from orchestrator.app.briefing_rules import body_fat_high_rule
    now = datetime.now(timezone.utc)
    fats = [14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0, 21.0, 22.0, 23.0]
    rows = [{"weight_kg": None, "body_fat_pct": v,
             "lean_mass_kg": None, "bmi": None,
             "recorded_at": now - timedelta(days=i)} for i, v in enumerate(fats)]
    latest = {"weight_kg": None, "body_fat_pct": 20.0,
              "lean_mass_kg": None, "bmi": None, "recorded_at": now}
    metrics = {"body": {"latest": latest, "recent_90d": [latest, *rows]}}
    assert body_fat_high_rule(metrics) is None


def test_body_fat_high_silent_when_no_body():
    from orchestrator.app.briefing_rules import body_fat_high_rule
    assert body_fat_high_rule({"body": None}) is None


def test_body_fat_high_silent_on_flat_baseline():
    """When all historical fats are identical, p90 == every point. Rule must
    stay silent to avoid weekly spam on a stable baseline."""
    from orchestrator.app.briefing_rules import body_fat_high_rule
    now = datetime.now(timezone.utc)
    fats = [18.0] * 10
    rows = [{"weight_kg": None, "body_fat_pct": v,
             "lean_mass_kg": None, "bmi": None,
             "recorded_at": now - timedelta(days=i)} for i, v in enumerate(fats)]
    latest = {"weight_kg": None, "body_fat_pct": 18.0,
              "lean_mass_kg": None, "bmi": None, "recorded_at": now}
    metrics = {"body": {"latest": latest, "recent_90d": [latest, *rows]}}
    assert body_fat_high_rule(metrics) is None


def test_body_no_data_fires_when_latest_is_15_days_old():
    from orchestrator.app.briefing_rules import body_no_data_rule
    now = datetime.now(timezone.utc)
    latest = {"weight_kg": 82.0, "body_fat_pct": None,
              "lean_mass_kg": None, "bmi": None,
              "recorded_at": now - timedelta(days=15)}
    metrics = {"body": {"latest": latest, "recent_90d": [latest]}}
    alert = body_no_data_rule(metrics)
    assert alert is not None
    assert alert.rule_id == "body.no_data.14d"
    assert alert.severity == "info"
    assert alert.throttle_hours == 168
    assert "15 days" in alert.message


def test_body_no_data_silent_when_latest_is_13_days_old():
    from orchestrator.app.briefing_rules import body_no_data_rule
    now = datetime.now(timezone.utc)
    latest = {"weight_kg": 82.0, "body_fat_pct": None,
              "lean_mass_kg": None, "bmi": None,
              "recorded_at": now - timedelta(days=13)}
    metrics = {"body": {"latest": latest, "recent_90d": [latest]}}
    assert body_no_data_rule(metrics) is None


def test_body_no_data_silent_when_body_is_none():
    from orchestrator.app.briefing_rules import body_no_data_rule
    assert body_no_data_rule({"body": None}) is None
