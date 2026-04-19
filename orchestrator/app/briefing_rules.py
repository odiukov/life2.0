"""Per-category briefing rules. Each rule is a pure function of metrics →
Alert | None. Rules are registered in RULES and aggregated by collect_alerts.
"""
from __future__ import annotations

from typing import Callable

from .alerts import Alert


def sleep_missing_data_rule(metrics: dict) -> Alert | None:
    if metrics.get("sleep"):
        return None
    return Alert(
        rule_id="sleep.no_data.1d",
        severity="info",
        message="no sleep data logged for yesterday",
        category="wellness",
        throttle_hours=24,
    )


RULES: list[Callable[[dict], Alert | None]] = [
    sleep_missing_data_rule,
]


def collect_alerts(metrics: dict) -> list[Alert]:
    out: list[Alert] = []
    for rule in RULES:
        a = rule(metrics)
        if a is not None:
            out.append(a)
    return out
