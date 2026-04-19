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


def body_weight_gain_rule(metrics: dict) -> Alert | None:
    body = metrics.get("body") or {}
    latest = body.get("latest")
    rows = body.get("recent_90d") or []
    if not latest or latest.get("weight_kg") is None:
        return None
    latest_ts = latest["recorded_at"]
    target = latest_ts - timedelta(days=7)
    ref = None
    best_delta = timedelta(days=3)  # strictly-less sentinel = matches < 3 days
    for r in rows:
        if r.get("weight_kg") is None:
            continue
        if r["recorded_at"] == latest_ts:
            continue
        d = abs(r["recorded_at"] - target)
        if d <= timedelta(days=2) and d < best_delta:
            ref, best_delta = r, d
    if ref is None:
        return None
    delta = latest["weight_kg"] - ref["weight_kg"]
    if delta < 1.5:
        return None
    msg = (f"weight +{delta:.1f} kg in 7 days "
           f"({ref['weight_kg']:.1f} → {latest['weight_kg']:.1f})")
    return Alert(
        rule_id="body.weight_gain.7d",
        severity="warn",
        message=msg,
        category="wellness",
        throttle_hours=24,
    )


RULES.append(body_weight_gain_rule)
