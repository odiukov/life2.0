"""Pure-function domain logic for recovery/readiness.

Shared by agents/recovery/app/executor.py AND orchestrator/app/recovery_context.py.
No DB, no LLM, no HTTP. Unit-testable in isolation.

Metrics contract (HealthKit-sourced after multi-user migration):
  - hrv_sdnn:             HRV standard-deviation of NN intervals, ms. Higher = more recovered.
  - rhr:                  Resting Heart Rate, bpm. Lower = more recovered.
  - sleep_efficiency_pct: % of time in bed actually asleep. Higher = more recovered.
  - sleep_duration_h:     Total sleep duration in hours. Higher = more recovered.

Legacy Garmin metrics (stress, bb_max) are no longer supported — the recovery
agent pulls from HealthKit via `/sync/health`; a callers-pass-the-right-shape
contract replaces the old Garmin Body Battery source.

All metrics can be None → the metric is skipped. <3 metrics available overall
→ bucket = 'unknown'.
"""
from __future__ import annotations

from typing import Any

_METRIC_LABELS = {
    "hrv_sdnn": "HRV",
    "rhr": "RHR",
    "sleep_efficiency_pct": "sleep eff.",
    "sleep_duration_h": "sleep h",
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


# (noise threshold, preference) per metric. 10% threshold for bucket gates
# matches the design spec §4.4 after the HealthKit switch.
_THRESHOLDS = {
    "hrv_sdnn":              (0.10, "higher"),
    "rhr":                   (0.10, "lower"),
    "sleep_efficiency_pct":  (0.10, "higher"),
    "sleep_duration_h":      (0.10, "higher"),
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
    delta: '+5%' / '-12%' — None when baseline missing or within ±1% noise floor.
    """
    if baseline == 0:
        return "·", None
    pct = (current - baseline) / baseline * 100.0
    if abs(pct) < 1.0:
        return "·", None
    if pct > 0:
        return "↑", f"+{pct:.0f}%"
    return "↓", f"{pct:.0f}%"


def compute_deltas(current: dict, baseline: dict) -> dict:
    """Return {metric: {value, dir, delta}} for all four metrics."""
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
    """Parse '+11%' / '-50%' / None → absolute magnitude, None → 0."""
    if not delta:
        return 0.0
    s = delta.replace("+", "").replace("%", "").strip()
    try:
        return abs(float(s))
    except ValueError:
        return 0.0


def format_top3(deltas: dict) -> list[dict]:
    """Return top-3 metrics by |delta|, for compact recovery rendering.

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


def baseline_mean(window: list[dict]) -> dict:
    """Compute per-metric mean across a baseline window.

    Skips None values per metric. Returns None for metrics with zero
    non-None observations.
    """
    out: dict[str, float | None] = {m: None for m in _THRESHOLDS}
    for key in out:
        values = [d[key] for d in window if d.get(key) is not None]
        out[key] = sum(values) / len(values) if values else None
    return out
