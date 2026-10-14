from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from body.domain.measurement import BodyMeasurement, measurement_line
from shared.ports.health_logs import HealthLogRow

AT = datetime(2026, 10, 12, 23, 30, tzinfo=UTC)  # 13 Oct in Moscow


def test_from_row_reads_known_keys_and_tolerates_junk() -> None:
    m = BodyMeasurement.from_row(
        HealthLogRow(
            "body_composition",
            AT,
            {
                "weight_kg": "82.5",
                "body_fat_pct": 18.2,
                "bmr_kcal": None,
                "body_age": "n/a",
                "lean_mass_kg": 67,
            },
            source="vihealth",
            agent="workout",
        )
    )
    assert (m.weight_kg, m.body_fat_pct, m.bmr_kcal, m.body_age, m.lean_mass_kg, m.source) == (
        82.5,
        18.2,
        None,
        None,
        67.0,
        "vihealth",
    )


def test_line_uses_local_date_and_only_present_metrics() -> None:
    m = BodyMeasurement.from_row(
        HealthLogRow("body_composition", AT, {"weight_kg": 82.5, "visceral_fat_grade": 7})
    )
    assert (
        measurement_line(m, ZoneInfo("Europe/Moscow"))
        == "- 2026-10-13 | weight=82.5kg | visceral_fat=7"
    )


def test_line_without_metrics() -> None:
    m = BodyMeasurement.from_row(HealthLogRow("body_composition", AT, {}))
    assert measurement_line(m, ZoneInfo("UTC")) == "- 2026-10-12 | (no metrics)"


def test_line_renders_all_legacy_metrics_in_order() -> None:
    m = BodyMeasurement.from_row(
        HealthLogRow(
            "body_composition",
            AT,
            {
                "weight_kg": 79.6,
                "body_fat_pct": 26.5,
                "muscle_kg": 54.6,
                "skeletal_muscle_kg": 33.1,
                "bmr_kcal": 1633,
                "visceral_fat_grade": 8,
                "body_age": 32,
                "body_score": 73,
            },
        )
    )
    assert measurement_line(m, ZoneInfo("UTC")) == (
        "- 2026-10-12 | weight=79.6kg | fat=26.5% | muscle=54.6kg | "
        "skeletal_muscle=33.1kg | bmr=1633kcal | visceral_fat=8 | body_age=32 | body_score=73"
    )
