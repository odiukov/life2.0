"""Briefing-side helper: compact recovery shape via shared.recovery domain logic.

Reuses the SAME bucket + deltas logic as agents/recovery/ — neither re-implements
the rule set. Returns None when data is insufficient (bucket='unknown').
"""
from __future__ import annotations

import logging
from datetime import date

from shared.db import fetch_recovery_metrics
from shared.recovery import compute_bucket, compute_deltas, format_top3

logger = logging.getLogger(__name__)


def _baseline_mean(window: list[dict]) -> dict:
    out = {"hrv": None, "rhr": None, "stress": None, "bb_max": None}
    for key in out:
        values = [d[key] for d in window if d.get(key) is not None]
        out[key] = sum(values) / len(values) if values else None
    return out


async def fetch_recovery_shape(target_date: date) -> dict | None:
    """Return {bucket, top3} or None when bucket='unknown' / no data."""
    try:
        metrics = await fetch_recovery_metrics(days=8)  # target + 7 baseline
    except Exception as e:
        logger.warning("fetch_recovery_metrics failed: %s", e)
        return None

    if not metrics:
        return None

    target_key = target_date.isoformat()
    current = metrics.get(target_key)
    if current is None:
        latest = sorted(metrics.keys(), reverse=True)
        if not latest:
            return None
        current = metrics[latest[0]]
        target_key = latest[0]

    baseline_days = [metrics[k] for k in sorted(metrics.keys(), reverse=True)
                     if k != target_key][:7]
    baseline = _baseline_mean(baseline_days)

    bucket = compute_bucket(current, baseline)
    if bucket == "unknown":
        return None

    deltas = compute_deltas(current, baseline)
    top3 = format_top3(deltas)
    return {"bucket": bucket, "top3": top3}
