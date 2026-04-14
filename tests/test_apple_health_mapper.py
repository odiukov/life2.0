from datetime import timezone
from sync_service.app.apple_health import map_body_composition


SAMPLE_PAYLOAD = {
    "data": [
        {"date": "2026-04-14 09:37:16 +0300", "qty": 79.6, "name": "Body Mass", "units": "kg"},
        {"date": "2026-04-14 09:37:16 +0300", "qty": 26.5, "name": "Body Fat Percentage", "units": "%"},
        {"date": "2026-04-14 09:37:16 +0300", "qty": 54.6, "name": "Lean Body Mass", "units": "kg"},
        {"date": "2026-04-14 09:37:16 +0300", "qty": 27.5, "name": "Body Mass Index", "units": "count"},
        {"date": "2026-04-14 09:37:16 +0300", "qty": 33.1, "name": "Skeletal Muscle Mass", "units": "kg"},
        {"date": "2026-04-14 09:37:16 +0300", "qty": 3.9, "name": "Bone Mass", "units": "kg"},
        # second measurement on a different day
        {"date": "2026-03-01 08:00:00 +0000", "qty": 81.0, "name": "Body Mass", "units": "kg"},
        {"date": "2026-03-01 08:00:00 +0000", "qty": 28.1, "name": "Body Fat Percentage", "units": "%"},
        # unknown metric — should be ignored
        {"date": "2026-04-14 09:37:16 +0300", "qty": 120, "name": "Heart Rate", "units": "bpm"},
    ]
}


def test_groups_by_date():
    rows = map_body_composition(SAMPLE_PAYLOAD)
    assert len(rows) == 2


def test_all_metrics_mapped():
    rows = map_body_composition(SAMPLE_PAYLOAD)
    april_row = next(r for r in rows if r["recorded_at"].date().isoformat() == "2026-04-14")
    data = april_row["data"]
    assert data["weight_kg"] == 79.6
    assert data["body_fat_pct"] == 26.5
    assert data["lean_mass_kg"] == 54.6
    assert data["bmi"] == 27.5
    assert data["skeletal_muscle_kg"] == 33.1
    assert data["bone_mass_kg"] == 3.9


def test_unknown_metric_ignored():
    rows = map_body_composition(SAMPLE_PAYLOAD)
    april_row = next(r for r in rows if r["recorded_at"].date().isoformat() == "2026-04-14")
    assert "heart_rate" not in april_row["data"]


def test_row_metadata():
    rows = map_body_composition(SAMPLE_PAYLOAD)
    for row in rows:
        assert row["agent"] == "workout"
        assert row["type"] == "body_composition"
        assert row["source"] == "apple_health"
        assert row["recorded_at"].tzinfo == timezone.utc


def test_empty_payload():
    assert map_body_composition({}) == []
    assert map_body_composition({"data": []}) == []
