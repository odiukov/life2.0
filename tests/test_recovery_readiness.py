"""Unit tests for shared.shared.recovery — pure-function domain logic.
No DB, no LLM, no I/O. Direction, thresholds, missing-metric handling."""
from shared.recovery import compute_bucket, compute_deltas, format_top3


# ---------------- compute_bucket ----------------

def test_bucket_recovered_all_four_metrics_better():
    current = {"hrv": 50, "rhr": 55, "stress": 20, "bb_max": 90}
    baseline = {"hrv": 45, "rhr": 60, "stress": 40, "bb_max": 80}
    assert compute_bucket(current, baseline) == "recovered"


def test_bucket_depleted_all_four_metrics_worse():
    current = {"hrv": 40, "rhr": 65, "stress": 60, "bb_max": 70}
    baseline = {"hrv": 45, "rhr": 60, "stress": 40, "bb_max": 85}
    assert compute_bucket(current, baseline) == "depleted"


def test_bucket_neutral_when_mixed():
    current = {"hrv": 50, "rhr": 65, "stress": 20, "bb_max": 70}   # hrv↑, rhr↑(worse), stress↓, bb↓
    baseline = {"hrv": 45, "rhr": 60, "stress": 40, "bb_max": 85}
    assert compute_bucket(current, baseline) == "neutral"


def test_bucket_unknown_when_fewer_than_three_metrics_available():
    current = {"hrv": 50, "rhr": None, "stress": None, "bb_max": None}
    baseline = {"hrv": 45, "rhr": None, "stress": None, "bb_max": None}
    assert compute_bucket(current, baseline) == "unknown"


def test_bucket_hrv_noise_floor_2pct():
    """HRV change within ±2% of baseline is not counted as better or worse."""
    current = {"hrv": 45.5, "rhr": 60, "stress": 40, "bb_max": 85}  # hrv +1.1% — inside noise
    baseline = {"hrv": 45, "rhr": 60, "stress": 40, "bb_max": 85}
    # Only the 3 unchanged metrics count; none of them cross threshold → neutral
    assert compute_bucket(current, baseline) == "neutral"


def test_bucket_missing_metric_skipped_not_counted_either_way():
    """Missing hrv with three other metrics 'better' → recovered."""
    current = {"hrv": None, "rhr": 55, "stress": 20, "bb_max": 90}
    baseline = {"hrv": 45, "rhr": 60, "stress": 40, "bb_max": 80}
    assert compute_bucket(current, baseline) == "recovered"


# ---------------- compute_deltas ----------------

def test_compute_deltas_hrv_percentage_and_dir():
    current = {"hrv": 50, "rhr": 55, "stress": 20, "bb_max": 90}
    baseline = {"hrv": 45, "rhr": 60, "stress": 40, "bb_max": 80}
    deltas = compute_deltas(current, baseline)
    assert deltas["hrv"]["dir"] == "↑"
    assert "%" in str(deltas["hrv"]["delta"])
    assert deltas["rhr"]["dir"] == "↓"
    assert deltas["stress"]["dir"] == "↓"


def test_compute_deltas_handles_none_baseline():
    current = {"hrv": 50, "rhr": None, "stress": None, "bb_max": None}
    baseline = {"hrv": None, "rhr": None, "stress": None, "bb_max": None}
    deltas = compute_deltas(current, baseline)
    # No baseline → values still present, direction neutral/dashed, delta None
    assert deltas["hrv"]["value"] == 50
    assert deltas["hrv"]["delta"] is None


# ---------------- format_top3 ----------------

def test_format_top3_picks_three_largest_abs_delta():
    deltas = {
        "hrv": {"value": 50, "dir": "↑", "delta": "+11%"},
        "rhr": {"value": 55, "dir": "↓", "delta": "-8%"},
        "stress": {"value": 20, "dir": "↓", "delta": "-50%"},
        "bb_max": {"value": 90, "dir": "↑", "delta": "+1%"},
    }
    top3 = format_top3(deltas)
    labels = [m["label"] for m in top3]
    assert len(top3) == 3
    # stress (-50%) and hrv (+11%) are larger-magnitude moves than bb_max (+1%)
    assert "stress" in labels
    assert "HRV" in labels or "hrv" in labels
    assert "body battery" not in labels  # smallest delta, excluded


def test_format_top3_fewer_than_three_metrics_available():
    """Only 2 metrics with data → return 2, don't crash."""
    deltas = {
        "hrv": {"value": 50, "dir": "↑", "delta": "+5%"},
        "rhr": {"value": 55, "dir": "↓", "delta": "-8%"},
        "stress": {"value": None, "dir": None, "delta": None},
        "bb_max": {"value": None, "dir": None, "delta": None},
    }
    top3 = format_top3(deltas)
    assert len(top3) == 2
