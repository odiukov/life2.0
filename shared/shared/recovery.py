"""Pure-function domain logic for recovery/readiness.

Shared by agents/recovery/app/executor.py AND orchestrator/app/recovery_context.py.
No DB, no LLM, no HTTP. Unit-testable in isolation.

Metrics contract:
  - hrv:     Heart Rate Variability. Higher = more recovered.
  - rhr:     Resting Heart Rate. Lower = more recovered.
  - stress:  Garmin daily stress 0–100. Lower = more recovered.
  - bb_max:  Garmin body battery peak. Higher = more recovered.

All metrics can be None → the metric is skipped. <3 metrics available
overall → bucket='unknown'.
"""
from __future__ import annotations

from typing import Any

_METRIC_LABELS = {
    "hrv": "HRV",
    "rhr": "RHR",
    "stress": "stress",
    "bb_max": "body battery",
}


def _cmp(current: float, baseline: float, threshold_pct: float,
         prefer: str) -> int:
    """Return +1 (better), -1 (worse), 0 (within noise).

    prefer='higher' → current > baseline*(1+threshold_pct) is better.
    prefer='lower'  → current < baseline*(1-threshold_pct) is better.
    """
    if baseline == 0:
        return 0
    if prefer == "higher":
        if current > baseline * (1 + threshold_pct):
            return 1
        if current < baseline * (1 - threshold_pct):
            return -1
        return 0
    # prefer == "lower"
    if current < baseline * (1 - threshold_pct):
        return 1
    if current > baseline * (1 + threshold_pct):
        return -1
    return 0


_THRESHOLDS = {
    "hrv":    (0.02, "higher"),  # 2% noise floor
    "rhr":    (0.02, "lower"),
    "stress": (0.10, "lower"),   # stress is noisier, 10% threshold
    "bb_max": (0.0,  "higher"),  # simple >= comparison (Garmin already smooths)
}


def compute_bucket(current: dict, baseline: dict) -> str:
    """Return 'recovered' | 'neutral' | 'depleted' | 'unknown'.

    Counts metrics where current is better than baseline; if 3+ better → recovered,
    3+ worse → depleted, <3 usable metrics → unknown, else neutral.
    """
    better = 0
    worse = 0
    available = 0
    for metric, (threshold, prefer) in _THRESHOLDS.items():
        c = current.get(metric)
        b = baseline.get(metric)
        if c is None or b is None:
            continue
        available += 1
        score = _cmp(float(c), float(b), threshold, prefer)
        if score > 0:
            better += 1
        elif score < 0:
            worse += 1

    if available < 3:
        return "unknown"
    if better >= 3:
        return "recovered"
    if worse >= 3:
        return "depleted"
    return "neutral"


def _format_delta(current: float, baseline: float, metric: str) -> tuple[str, str | None]:
    """Return (dir_arrow, delta_string_or_None).

    dir: '↑' | '↓' | '·' (stable/noise)
    delta: '+5%' / '-12' etc. — None when baseline missing or metric uses absolute scale.
    """
    _threshold, prefer = _THRESHOLDS[metric]
    if baseline == 0:
        return "·", None
    pct = (current - baseline) / baseline * 100.0
    if abs(pct) < 1.0:  # presentation noise floor — don't bother showing ±0.X%
        return "·", None
    if pct > 0:
        return "↑", f"+{pct:.0f}%"
    return "↓", f"{pct:.0f}%"


def compute_deltas(current: dict, baseline: dict) -> dict:
    """Return {metric: {value, dir, delta}} for all four metrics.

    Missing current → value=None, dir=None, delta=None.
    Missing baseline but present current → value=current, dir='·', delta=None.
    """
    out: dict[str, dict] = {}
    for metric in _THRESHOLDS:
        c = current.get(metric)
        b = baseline.get(metric)
        if c is None:
            out[metric] = {"value": None, "dir": None, "delta": None}
            continue
        if b is None:
            out[metric] = {"value": c, "dir": "·", "delta": None}
            continue
        arrow, delta = _format_delta(float(c), float(b), metric)
        out[metric] = {"value": c, "dir": arrow, "delta": delta}
    return out


def _delta_magnitude(delta: str | None) -> float:
    """Parse '+11%' / '-50%' / '-8' / None → absolute magnitude, None → 0."""
    if not delta:
        return 0.0
    s = delta.replace("+", "").replace("%", "").strip()
    try:
        return abs(float(s))
    except ValueError:
        return 0.0


def format_top3(deltas: dict) -> list[dict]:
    """Return top-3 metrics by |delta|, for briefing rendering.

    Each item: {label, value, dir, delta}. Skips metrics with value=None.
    Stable ordering on ties (preserves insertion order of _THRESHOLDS).
    """
    candidates = []
    for metric in _THRESHOLDS:
        d = deltas.get(metric) or {}
        if d.get("value") is None:
            continue
        candidates.append({
            "label": _METRIC_LABELS[metric],
            "value": d["value"],
            "dir": d.get("dir"),
            "delta": d.get("delta"),
        })
    candidates.sort(key=lambda m: -_delta_magnitude(m.get("delta")))
    return candidates[:3]
