"""Prompt builders for the 3 recovery agent skills."""
from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from shared.db import fetch_recovery_metrics
from shared.grounding import GROUNDING_RULES
from shared.peer_chip_rules import PEER_CHIP_RULES
from shared.personas import IDENTITY, VOCAB
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


async def build_recovery_prompt(
    task: str,
    params: dict,
    peer_artifacts: dict | None = None,
) -> str:
    """Build prompts for 3 skills. All consume fetch_recovery_metrics(days=7 or 14)."""
    user_id = UUID(params["user_id"])
    days = 14 if task == "analyze_recovery_trend" else 8
    metrics = await fetch_recovery_metrics(user_id, days=days)

    if not metrics:
        return (
            f"{IDENTITY['recovery']}\n\n"
            "There is no recovery data available yet (Garmin sync may be "
            "empty or offline). Tell the user: readiness unknown — come "
            "back after the next sync.\n\n" + GROUNDING_RULES
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

    peer = peer_artifacts if peer_artifacts is not None else (params.get("peer_artifacts") or {})
    peer_section = ""
    if peer:
        chunks = []
        for name in ("sleep", "workout", "nutrition", "mood"):
            text = peer.get(name)
            if text and text.strip() and text != "(данные недоступны)":
                chunks.append(f"### {name}\n{text}")
        if chunks:
            peer_section = "\n## Peer context\n" + "\n\n".join(chunks)
    chip_block = f"\n{PEER_CHIP_RULES}" if peer_section else ""

    base = (
        f"{IDENTITY['recovery']}\n\n"
        f"## Snapshot\n{snapshot}\n\n"
        f"## Last 7 days\n{history_lines}\n"
        f"{peer_section}\n\n"
        f"## Vocabulary you may invoke (only when grounded by data)\n"
        f"{VOCAB['recovery']}\n\n"
        f"## User request\n"
        f"Task: {task}\n"
        f"Params: {params}\n"
        f"{chip_block}"
    )

    if task == "get_readiness":
        return base + (
            "\nState the bucket directly, then give one sentence per moved "
            "metric (HRV, RHR, stress, body battery) with its direction and "
            "magnitude grounded in the data. 3–5 lines plain text.\n\n"
            + GROUNDING_RULES
        )

    if task == "analyze_recovery_trend":
        return base + (
            "\n6–10 lines plain text: (1) per-metric 7-day trend, "
            "(2) outlier days with a mechanism (e.g. allostatic load), "
            "(3) one correlation observation grounded in peer context if "
            "present. No markdown.\n\n" + GROUNDING_RULES
        )

    if task == "get_recommendations":
        return base + (
            "\n4–6 lines plain text with 2–3 concrete recovery-domain actions "
            "+ the 'why' grounded in the bucket and recent metrics. Redirect "
            "training prescriptions to /workout. No markdown.\n\n"
            + GROUNDING_RULES
        )

    return base + "\n\n" + GROUNDING_RULES
