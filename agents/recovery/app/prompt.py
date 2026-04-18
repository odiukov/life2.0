"""Prompt builders for the 3 recovery agent skills."""
from __future__ import annotations

from datetime import date, timedelta
from zoneinfo import ZoneInfo

from shared.db import fetch_recovery_metrics
from shared.recovery import baseline_mean, compute_bucket

_KYIV = ZoneInfo("Europe/Kyiv")


def _format_day(date_key: str, metrics: dict) -> str:
    """Single-line rendering of one day's metrics for the prompt."""
    bits = []
    if metrics.get("hrv") is not None:
        bits.append(f"HRV={metrics['hrv']}")
    if metrics.get("rhr") is not None:
        bits.append(f"RHR={metrics['rhr']}")
    if metrics.get("stress") is not None:
        bits.append(f"stress={metrics['stress']}")
    if metrics.get("bb_max") is not None:
        bb_min_str = str(metrics['bb_min']) if metrics.get('bb_min') is not None else "?"
        bits.append(f"body_battery={bb_min_str}/{metrics['bb_max']}")
    if metrics.get("sleep_score") is not None:
        bits.append(f"sleep_score={metrics['sleep_score']}")
    return f"{date_key}: " + ", ".join(bits)


async def build_recovery_prompt(task: str, params: dict) -> str:
    """Build prompts for 3 skills. All consume fetch_recovery_metrics(days=7 or 14)."""
    days = 14 if task == "analyze_recovery_trend" else 8
    metrics = await fetch_recovery_metrics(days=days)

    if not metrics:
        return (
            "There is no recovery data available yet (Garmin sync may be empty "
            "or offline). Tell the user: readiness unknown — come back after the "
            "next sync."
        )

    # Split into 'current' (latest day) + 'baseline' (previous up to 7 days).
    sorted_keys = sorted(metrics.keys(), reverse=True)
    latest_key = sorted_keys[0]
    current = metrics[latest_key]
    baseline_days = [metrics[k] for k in sorted_keys[1:8]]
    baseline = baseline_mean(baseline_days)

    bucket = compute_bucket(current, baseline)

    # Format recent days for the prompt context.
    history_lines = "\n".join(
        _format_day(k, metrics[k]) for k in sorted_keys[:7]
    )

    snapshot = (
        f"Bucket: {bucket}\n"
        f"Latest ({latest_key}): HRV={current.get('hrv')}, RHR={current.get('rhr')}, "
        f"stress={current.get('stress')}, body_battery={current.get('bb_min')}/{current.get('bb_max')}\n"
        f"7-day baseline: HRV={baseline.get('hrv')}, RHR={baseline.get('rhr')}, "
        f"stress={baseline.get('stress')}, body_battery_max={baseline.get('bb_max')}"
    )

    base = (
        f"You are a recovery / readiness assistant. Recovery metrics synced from Garmin.\n\n"
        f"## Snapshot\n{snapshot}\n\n"
        f"## Last 7 days\n{history_lines}\n\n"
        f"## Task\n{task}\n"
        f"## Params\n{params}\n"
    )

    if task == "get_readiness":
        return base + (
            "\nRespond in the user's language. State the bucket directly, then "
            "give one sentence per moved metric (HRV, RHR, stress, body battery) "
            "with its direction and magnitude. Plain text, 3–5 lines, no markdown."
        )

    if task == "analyze_recovery_trend":
        return base + (
            "\nRespond in the user's language: (1) per-metric 7-day trend direction, "
            "(2) any outlier days and what might explain them, (3) one correlation "
            "observation if obvious (e.g., HRV dips on high-stress days). 4–6 lines "
            "plain text, no markdown."
        )

    if task == "get_recommendations":
        return base + (
            "\nRespond in the user's language with 2–3 short actionable recommendations "
            "based on the bucket + recent metrics. Concrete, not generic. Plain text, "
            "no markdown."
        )

    return base
