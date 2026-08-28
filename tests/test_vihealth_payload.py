from datetime import datetime, timezone
from unittest.mock import patch


def test_build_payload_from_pdf_emits_widened_fields():
    """build_payload_from_pdf (pdfplumber path) maps all metrics."""
    from sync_service.app.vihealth_pdf import build_payload_from_pdf

    fake_result = {
        "recorded_at": datetime(2026, 4, 14, 9, 37, 16, tzinfo=timezone.utc),
        "metrics": {
            "weight_kg": 79.6, "body_fat_pct": 26.5, "bmi": 27.5,
            "skeletal_muscle_kg": 33.1, "bone_mass_kg": 3.9,
            "body_fat_kg": 21.1, "protein_kg": 11.7, "body_water_kg": 42.9,
            "muscle_kg": 54.6, "visceral_fat_grade": 8,
            "bmr_kcal": 1633, "fat_free_kg": 58.5,
            "subcutaneous_fat_pct": 18.9, "body_age": 32, "body_score": 73,
        },
    }

    with patch("sync_service.app.vihealth_pdf.parse_vihealth_pdf", return_value=fake_result):
        payload = build_payload_from_pdf(b"ignored")

    names = {e["name"] for e in payload["data"]}
    for required in {
        "Body Mass", "Body Fat Percentage", "Body Mass Index",
        "Skeletal Muscle Mass", "Bone Mass", "Lean Body Mass",
        "Basal Metabolic Rate", "Visceral Fat Grade", "Body Age",
        "Body Score", "Subcutaneous Fat Percentage", "Protein Mass",
        "Body Water", "Muscle Mass", "Body Fat Mass", "Fat Free Body Weight",
    }:
        assert required in names, f"missing {required}"
