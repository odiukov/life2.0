from datetime import UTC, datetime

from sync.domain.body import map_body_composition
from sync_fixtures import BODY_ENTRIES


def test_groups_one_weigh_in_per_local_day_and_ignores_unknown_metrics() -> None:
    rows = sorted(map_body_composition(BODY_ENTRIES), key=lambda r: r.recorded_at)
    assert [r.recorded_at for r in rows] == [
        datetime(2026, 3, 1, 8, 0, tzinfo=UTC),
        datetime(2026, 4, 14, 6, 37, 16, tzinfo=UTC),
    ]
    assert rows[1].data == {
        "weight_kg": 79.6,
        "body_fat_pct": 26.5,
        "lean_mass_kg": 54.6,
        "bmi": 27.5,
        "skeletal_muscle_kg": 33.1,
        "bone_mass_kg": 3.9,
    }
    assert (rows[1].agent, rows[1].type, rows[1].source) == (
        "workout",
        "body_composition",
        "apple_health",
    )


def test_body_grouping_uses_the_payloads_local_date() -> None:
    # Both weigh-ins fall on 2026-04-14 in UTC (20:30 and 21:10), so the legacy code merged them into one
    # row and the later weight overwrote the earlier. By the payload's own dates they are two days.
    entries = [
        {"date": "2026-04-14 23:30:00 +0300", "qty": 80.0, "name": "Body Mass"},
        {"date": "2026-04-15 00:10:00 +0300", "qty": 79.0, "name": "Body Mass"},
        {"date": "2026-04-15 00:10:05 +0300", "qty": 25.0, "name": "Body Fat Percentage"},
    ]
    rows = sorted(map_body_composition(entries), key=lambda r: r.recorded_at)
    assert [r.data for r in rows] == [
        {"weight_kg": 80.0},
        {"weight_kg": 79.0, "body_fat_pct": 25.0},
    ]
    assert rows[1].recorded_at == datetime(2026, 4, 14, 21, 10, tzinfo=UTC)


def test_widened_metrics_and_rounding() -> None:
    names = {
        "Basal Metabolic Rate": "bmr_kcal",
        "Visceral Fat Grade": "visceral_fat_grade",
        "Body Age": "body_age",
        "Body Score": "body_score",
        "Subcutaneous Fat Percentage": "subcutaneous_fat_pct",
        "Protein Mass": "protein_kg",
        "Body Water": "body_water_kg",
        "Muscle Mass": "muscle_kg",
        "Body Fat Mass": "body_fat_kg",
        "Fat Free Body Weight": "fat_free_kg",
    }
    entries = [
        {"date": "2026-04-14 09:37:16 +0000", "qty": 12.3456, "name": name} for name in names
    ]
    [row] = map_body_composition(entries)
    assert row.data == dict.fromkeys(names.values(), 12.35)


def test_empty_bad_dates_and_null_values() -> None:
    assert map_body_composition([]) == []
    assert map_body_composition([{"date": "", "qty": 1, "name": "Body Mass"}]) == []
    assert map_body_composition([{"date": "garbage", "qty": 1, "name": "Body Mass"}]) == []
    assert (
        map_body_composition(
            [{"date": "2026-04-14 09:00:00 +0000", "qty": None, "name": "Body Mass"}]
        )
        == []
    )
    [row] = map_body_composition([{"date": "2026-04-14", "qty": 70, "name": "Body Mass"}])
    assert row.recorded_at == datetime(2026, 4, 14, tzinfo=UTC)
