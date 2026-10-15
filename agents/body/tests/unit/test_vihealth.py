from datetime import UTC, datetime
from pathlib import Path

from body.domain.vihealth import (
    ROW_KEYS,
    fallback_time,
    looks_like_vihealth,
    measured_at,
    metrics_from_tables,
    metrics_from_text,
    profile_from_text,
    row_data,
)

TEXT = (Path(__file__).parents[1] / "fixtures" / "vihealth_text.txt").read_text("utf-8")
TABLES = [
    [
        ["Weight", "81.4(60.0–81.2)", "100%", "High"],
        ["Body fat", "14.8(9.6–16.0)", "18.2%", "Standard"],
        ["Muscle", "63,1", "", ""],
        [None, "x"],
    ],
    [
        ["Visceral fat grade", "8"],
        ["Basal metabolic rate", "1780 kcal"],
        ["SMI", "8.1 kg/m²"],
        ["Body age", "33"],
    ],
]


def test_text_metrics_and_time() -> None:
    assert metrics_from_text(TEXT) == {"bmi": 25.1, "body_fat_pct": 18.2}
    assert measured_at(TEXT) == datetime(2026, 10, 12, 9, 6, 31, tzinfo=UTC)
    assert measured_at("no time here") is None


def test_table_metrics_accept_commas_and_units() -> None:
    assert metrics_from_tables(TABLES) == {
        "weight_kg": 81.4,
        "body_fat_kg": 14.8,
        "muscle_kg": 63.1,
        "visceral_fat_grade": 8.0,
        "bmr_kcal": 1780.0,
        "smi": 8.1,
        "body_age": 33.0,
    }


def test_row_data_keeps_known_keys_rounds_and_derives_lean_mass() -> None:
    data = row_data({"weight_kg": 81.4, "body_fat_kg": 14.8, "smi": 8.1, "bmi": 25.123})
    assert data == {"weight_kg": 81.4, "body_fat_kg": 14.8, "lean_mass_kg": 66.6, "bmi": 25.12}
    assert "smi" not in ROW_KEYS


def test_profile_from_text() -> None:
    assert profile_from_text(TEXT) == {
        "sex": "male",
        "age": 35,
        "height_cm": 180.0,
        "weight_kg": 81.4,
    }


def test_fallback_time_is_stable_per_file() -> None:
    assert fallback_time(b"a") == fallback_time(b"a") != fallback_time(b"b")
    assert fallback_time(b"a").tzinfo is UTC
    assert fallback_time(b"a").year >= 2000


def test_recognizes_reports() -> None:
    assert looks_like_vihealth(TEXT)
    assert not looks_like_vihealth("Account Statement\nPayoneer")


def test_distinct_files_with_the_same_fallback_day_have_distinct_times() -> None:
    first = fallback_time(b"%PDF-report-119")
    second = fallback_time(b"%PDF-report-127")
    assert first.date() == second.date()
    assert first != second
    assert first == fallback_time(b"%PDF-report-119")
