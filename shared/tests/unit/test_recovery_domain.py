"""Unit tests for shared.domain.recovery — pure-function domain logic.
No DB, no LLM, no I/O. Direction, thresholds, missing-metric handling.

HealthKit-sourced metrics (post multi-user-auth migration):
  - hrv_sdnn (ms, higher=better)
  - rhr (bpm, lower=better)
  - sleep_efficiency_pct (higher=better)
  - sleep_duration_h (higher=better)
Threshold for bucket gates: 10%."""

from shared.domain.recovery import baseline_mean, compute_bucket, compute_deltas, format_top3

# ---------------- compute_bucket ----------------


def test_bucket_recovered_all_four_metrics_better():
    current = {"hrv_sdnn": 60, "rhr": 50, "sleep_efficiency_pct": 95, "sleep_duration_h": 9.0}
    baseline = {"hrv_sdnn": 45, "rhr": 60, "sleep_efficiency_pct": 80, "sleep_duration_h": 7.0}
    assert compute_bucket(current, baseline) == "recovered"


def test_bucket_depleted_all_four_metrics_worse():
    current = {"hrv_sdnn": 35, "rhr": 70, "sleep_efficiency_pct": 65, "sleep_duration_h": 5.5}
    baseline = {"hrv_sdnn": 45, "rhr": 60, "sleep_efficiency_pct": 85, "sleep_duration_h": 7.5}
    assert compute_bucket(current, baseline) == "depleted"


def test_bucket_neutral_when_mixed():
    # hrv↑ better, rhr↑ worse, sleep_eff unchanged, sleep_dur unchanged → 1 better + 1 worse
    current = {"hrv_sdnn": 55, "rhr": 70, "sleep_efficiency_pct": 85, "sleep_duration_h": 7.5}
    baseline = {"hrv_sdnn": 45, "rhr": 60, "sleep_efficiency_pct": 85, "sleep_duration_h": 7.5}
    assert compute_bucket(current, baseline) == "neutral"


def test_bucket_unknown_when_fewer_than_three_metrics_available():
    current = {"hrv_sdnn": 50, "rhr": None, "sleep_efficiency_pct": None, "sleep_duration_h": None}
    baseline = {"hrv_sdnn": 45, "rhr": None, "sleep_efficiency_pct": None, "sleep_duration_h": None}
    assert compute_bucket(current, baseline) == "unknown"


def test_bucket_hrv_noise_floor_10pct():
    """HRV change within ±10% of baseline is not counted as better or worse."""
    # hrv_sdnn: +1.1% — well inside 10% noise; other 3 unchanged → neutral.
    current = {"hrv_sdnn": 45.5, "rhr": 60, "sleep_efficiency_pct": 85, "sleep_duration_h": 7.5}
    baseline = {"hrv_sdnn": 45, "rhr": 60, "sleep_efficiency_pct": 85, "sleep_duration_h": 7.5}
    assert compute_bucket(current, baseline) == "neutral"


def test_bucket_missing_metric_skipped_not_counted_either_way():
    """Missing hrv_sdnn with three other metrics 'better' → recovered."""
    current = {"hrv_sdnn": None, "rhr": 50, "sleep_efficiency_pct": 95, "sleep_duration_h": 9.0}
    baseline = {"hrv_sdnn": 45, "rhr": 60, "sleep_efficiency_pct": 80, "sleep_duration_h": 7.0}
    assert compute_bucket(current, baseline) == "recovered"


# ---------------- compute_deltas ----------------


def test_compute_deltas_hrv_percentage_and_dir():
    current = {"hrv_sdnn": 50, "rhr": 55, "sleep_efficiency_pct": 95, "sleep_duration_h": 9.0}
    baseline = {"hrv_sdnn": 45, "rhr": 60, "sleep_efficiency_pct": 80, "sleep_duration_h": 7.0}
    deltas = compute_deltas(current, baseline)
    assert deltas["hrv_sdnn"]["dir"] == "↑"
    assert "%" in str(deltas["hrv_sdnn"]["delta"])
    assert deltas["rhr"]["dir"] == "↓"
    assert deltas["sleep_efficiency_pct"]["dir"] == "↑"


def test_compute_deltas_handles_none_baseline():
    current = {"hrv_sdnn": 50, "rhr": None, "sleep_efficiency_pct": None, "sleep_duration_h": None}
    baseline = {
        "hrv_sdnn": None,
        "rhr": None,
        "sleep_efficiency_pct": None,
        "sleep_duration_h": None,
    }
    deltas = compute_deltas(current, baseline)
    # No baseline → values still present, direction neutral/dashed, delta None
    assert deltas["hrv_sdnn"]["value"] == 50
    assert deltas["hrv_sdnn"]["delta"] is None


# ---------------- format_top3 ----------------


def test_format_top3_picks_three_largest_abs_delta():
    deltas = {
        "hrv_sdnn": {"value": 50, "dir": "↑", "delta": "+11%"},
        "rhr": {"value": 55, "dir": "↓", "delta": "-8%"},
        "sleep_efficiency_pct": {"value": 95, "dir": "↑", "delta": "+19%"},
        "sleep_duration_h": {"value": 7.1, "dir": "↑", "delta": "+1%"},
    }
    top3 = format_top3(deltas)
    labels = [m["label"] for m in top3]
    assert len(top3) == 3
    # sleep eff (+19%) and hrv (+11%) and rhr (-8%) are the three largest;
    # sleep_duration_h (+1%) is the smallest, excluded.
    assert "sleep eff." in labels
    assert "HRV" in labels
    assert "RHR" in labels
    assert "sleep h" not in labels


def test_format_top3_fewer_than_three_metrics_available():
    """Only 2 metrics with data → return 2, don't crash."""
    deltas = {
        "hrv_sdnn": {"value": 50, "dir": "↑", "delta": "+5%"},
        "rhr": {"value": 55, "dir": "↓", "delta": "-8%"},
        "sleep_efficiency_pct": {"value": None, "dir": None, "delta": None},
        "sleep_duration_h": {"value": None, "dir": None, "delta": None},
    }
    top3 = format_top3(deltas)
    assert len(top3) == 2


# ---------------- baseline_mean ----------------


def test_baseline_mean_averages_non_none_values():
    from shared.domain.recovery import baseline_mean

    window = [
        {"hrv_sdnn": 40, "rhr": 60, "sleep_efficiency_pct": 80, "sleep_duration_h": 7.0},
        {"hrv_sdnn": 50, "rhr": 58, "sleep_efficiency_pct": 90, "sleep_duration_h": 8.0},
    ]
    result = baseline_mean(window)
    assert result["hrv_sdnn"] == 45
    assert result["rhr"] == 59
    assert result["sleep_efficiency_pct"] == 85
    assert result["sleep_duration_h"] == 7.5


def test_baseline_mean_skips_none_values():
    from shared.domain.recovery import baseline_mean

    window = [
        {"hrv_sdnn": 40, "rhr": None, "sleep_efficiency_pct": None, "sleep_duration_h": 7.0},
        {"hrv_sdnn": 50, "rhr": 58, "sleep_efficiency_pct": None, "sleep_duration_h": None},
    ]
    result = baseline_mean(window)
    assert result["hrv_sdnn"] == 45
    assert result["rhr"] == 58  # only 1 non-None value
    assert result["sleep_efficiency_pct"] is None  # all None
    assert result["sleep_duration_h"] == 7.0


def test_baseline_mean_empty_window():
    from shared.domain.recovery import baseline_mean

    result = baseline_mean([])
    assert all(v is None for v in result.values())


def test_recovered_when_all_four_metrics_improve():
    # All 4 better by >10% vs baseline
    current = {
        "hrv_sdnn": 60.0,  # +25% vs 48
        "rhr": 50.0,  # -12% vs 57 → better (lower)
        "sleep_efficiency_pct": 95.0,  # +14% vs 83
        "sleep_duration_h": 8.5,  # +21% vs 7.0
    }
    baseline = {
        "hrv_sdnn": 48.0,
        "rhr": 57.0,
        "sleep_efficiency_pct": 83.0,
        "sleep_duration_h": 7.0,
    }
    assert compute_bucket(current, baseline) == "recovered"


def test_depleted_when_3_metrics_worsen():
    current = {
        "hrv_sdnn": 38.0,  # -21% vs 48 → worse
        "rhr": 64.0,  # +12% vs 57 → worse (higher bad)
        "sleep_efficiency_pct": 72.0,  # -13% vs 83 → worse
        "sleep_duration_h": 7.0,  # unchanged vs 7.0 → neutral
    }
    baseline = {
        "hrv_sdnn": 48.0,
        "rhr": 57.0,
        "sleep_efficiency_pct": 83.0,
        "sleep_duration_h": 7.0,
    }
    assert compute_bucket(current, baseline) == "depleted"


def test_unknown_when_fewer_than_three_metrics():
    current = {"hrv_sdnn": 50.0, "rhr": 55.0}
    baseline = {"hrv_sdnn": 48.0, "rhr": 57.0}
    assert compute_bucket(current, baseline) == "unknown"


def test_neutral_when_mixed_signals():
    # 1 better, 1 worse, 2 neutral (within threshold)
    current = {
        "hrv_sdnn": 55.0,  # +15% vs 48 → better
        "rhr": 65.0,  # +14% → worse
        "sleep_efficiency_pct": 85.0,  # +2.4% → neutral (within 10% threshold)
        "sleep_duration_h": 7.1,  # +1.4% → neutral
    }
    baseline = {
        "hrv_sdnn": 48.0,
        "rhr": 57.0,
        "sleep_efficiency_pct": 83.0,
        "sleep_duration_h": 7.0,
    }
    assert compute_bucket(current, baseline) == "neutral"


def test_legacy_metric_names_are_ignored():
    """Passing old (hrv, bb_max, stress) keys must not count toward the bucket."""
    current = {"hrv": 100, "bb_max": 90, "stress": 10}
    baseline = {"hrv": 50, "bb_max": 40, "stress": 50}
    # Only legacy keys present → no HealthKit metric matches → unknown
    assert compute_bucket(current, baseline) == "unknown"


def test_compute_deltas_shape():
    current = {"hrv_sdnn": 55, "rhr": 55, "sleep_efficiency_pct": 88, "sleep_duration_h": 7.2}
    baseline = {"hrv_sdnn": 50, "rhr": 60, "sleep_efficiency_pct": 80, "sleep_duration_h": 7.0}
    d = compute_deltas(current, baseline)
    assert set(d.keys()) == {"hrv_sdnn", "rhr", "sleep_efficiency_pct", "sleep_duration_h"}
    assert d["hrv_sdnn"]["dir"] == "↑"
    assert d["rhr"]["dir"] == "↓"


def test_format_top3_ranks_by_magnitude():
    deltas = {
        "hrv_sdnn": {"value": 55, "dir": "↑", "delta": "+10%"},
        "rhr": {"value": 50, "dir": "↓", "delta": "-12%"},
        "sleep_efficiency_pct": {"value": 90, "dir": "↑", "delta": "+5%"},
        "sleep_duration_h": {"value": 7.5, "dir": "↑", "delta": "+7%"},
    }
    top = format_top3(deltas)
    assert len(top) == 3
    # Ranking: -12% rhr, +10% hrv, +7% sleep_duration_h
    labels = [t["label"] for t in top]
    assert labels[0] == "RHR"
    assert labels[1] == "HRV"
    assert labels[2] == "sleep h"


def test_baseline_mean_with_nones():
    window = [
        {"hrv_sdnn": 50, "rhr": 60, "sleep_efficiency_pct": None, "sleep_duration_h": 7.0},
        {"hrv_sdnn": 55, "rhr": 58, "sleep_efficiency_pct": 85, "sleep_duration_h": 7.5},
        {"hrv_sdnn": 52, "rhr": None, "sleep_efficiency_pct": 82, "sleep_duration_h": 7.2},
    ]
    b = baseline_mean(window)
    assert abs(b["hrv_sdnn"] - (50 + 55 + 52) / 3) < 0.01
    assert abs(b["rhr"] - (60 + 58) / 2) < 0.01
    assert abs(b["sleep_efficiency_pct"] - (85 + 82) / 2) < 0.01
    assert abs(b["sleep_duration_h"] - (7.0 + 7.5 + 7.2) / 3) < 0.01


def test_healthkit_baseline_mean_empty_window():
    b = baseline_mean([])
    assert all(v is None for v in b.values())
