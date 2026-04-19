"""Per-category briefing rules. Each rule is a pure function of metrics →
Alert | None. Rules are registered in RULES and aggregated by collect_alerts.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


def medication_missed_rule(metrics: dict) -> Alert | None:
    med = metrics.get("medication") or {}
    active = med.get("active") or []
    if not active:
        return None
    logs = med.get("logs") or []
    now = datetime.now(timezone.utc)
    last_by_name: dict[str, datetime] = {}
    for r in logs:
        name = r.get("name")
        ts = r.get("recorded_at")
        if name and ts and (name not in last_by_name or ts > last_by_name[name]):
            last_by_name[name] = ts
    missed: list[str] = []
    for m in active:
        n = m.get("name")
        last = last_by_name.get(n)
        if last is None or (now - last) >= timedelta(days=2):
            missed.append(n)
    if not missed:
        return None
    msg = "missed " + ", ".join(missed) + " for 2+ days"
    return Alert(
        rule_id="medication.missed.2d",
        severity="warn",
        message=msg,
        category="wellness",
        throttle_hours=24,
    )


RULES.append(medication_missed_rule)
