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
