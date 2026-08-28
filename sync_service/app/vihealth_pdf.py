"""Parser for ViHealth body composition PDF reports (LePulse scales).

Extracts key metrics from the PDF and returns them in the same dict format
as apple_health.map_body_composition expects, so do_body_sync() can reuse it.
"""

import re
from datetime import datetime, timezone
from typing import Any

try:
    import pdfplumber
except ImportError:
    pdfplumber = None  # type: ignore


# Measurement row label → internal key
_COMPOSITION_KEYS: dict[str, str] = {
    "Weight": "weight_kg",
    "Body fat": "body_fat_kg",
    "Bone mass": "bone_mass_kg",
    "Protein": "protein_kg",
    "Body water": "body_water_kg",
    "Muscle": "muscle_kg",
    "Skeletal muscle": "skeletal_muscle_kg",
}

# "Other indicators" label → internal key
_OTHER_KEYS: dict[str, str] = {
    "Visceral fat grade": "visceral_fat_grade",
    "Basal metabolic rate": "bmr_kcal",
    "Fat-free body weight": "fat_free_kg",
    "Subcutaneous fat": "subcutaneous_fat_pct",
    "SMI": "smi",
    "Body age": "body_age",
}


def _parse_measurement(value_str: str) -> float | None:
    """Extract leading number from strings like '79.6(54.1–73.1)' or '79.6'."""
    m = re.match(r"^\s*([\d.]+)", value_str.replace(",", "."))
    return float(m.group(1)) if m else None


def _parse_datetime(text: str) -> datetime | None:
    """Find 'DD Mon YYYY, HH:MM:SS' in the PDF text."""
    # e.g. "14 Apr 2026, 09:37:16"
    m = re.search(r"(\d{1,2}\s+\w+\s+\d{4},\s*\d{2}:\d{2}:\d{2})", text)
    if m:
        try:
            return datetime.strptime(m.group(1).strip(), "%d %b %Y, %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            pass
    return None


def parse_vihealth_pdf(pdf_bytes: bytes) -> dict[str, Any]:
    """Parse ViHealth PDF bytes and return a body composition data dict.

    Returns:
        {
            "recorded_at": datetime (UTC) or None if not found,
            "metrics": { "weight_kg": float, "body_fat_pct": float, ... }
        }
    Raises RuntimeError if pdfplumber is not installed or PDF cannot be parsed.
    """
    if pdfplumber is None:
        raise RuntimeError("pdfplumber is not installed")

    import io

    metrics: dict[str, Any] = {}
    recorded_at: datetime | None = None

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

        # Try to parse the measurement date/time from text
        recorded_at = _parse_datetime(full_text)

        # BMI is usually in plain text as "27.5" near "BMI"
        bmi_m = re.search(r"BMI\D{0,20}?([\d.]+)", full_text)
        if bmi_m:
            metrics["bmi"] = float(bmi_m.group(1))

        # Body fat % appears near "Body fat rate" or "26.5" under that section
        fat_pct_m = re.search(r"Body fat rate\D{0,30}?([\d.]+)", full_text)
        if fat_pct_m:
            metrics["body_fat_pct"] = float(fat_pct_m.group(1))

        # Extract tables
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if not row or not row[0]:
                        continue
                    label = str(row[0]).strip()

                    # Body composition table: [label, measurement, proportion, evaluation]
                    if label in _COMPOSITION_KEYS and len(row) >= 2:
                        val = _parse_measurement(str(row[1]))
                        if val is not None:
                            metrics[_COMPOSITION_KEYS[label]] = val

                    # Other indicators: [label, value]
                    if label in _OTHER_KEYS and len(row) >= 2:
                        val_str = str(row[1] or "").strip()
                        # strip units like "kcal", "kg/m²"
                        num_m = re.match(r"([\d.]+)", val_str.replace(",", "."))
                        if num_m:
                            metrics[_OTHER_KEYS[label]] = float(num_m.group(1))

    return {"recorded_at": recorded_at, "metrics": metrics}


def build_payload_from_pdf(pdf_bytes: bytes) -> dict[str, Any]:
    """Convert parsed ViHealth PDF into the apple_health payload format.

    Returns a dict compatible with map_body_composition():
    { "data": [{"date": "...", "qty": ..., "name": "...", "units": "..."}, ...] }
    """
    result = parse_vihealth_pdf(pdf_bytes)
    metrics = result["metrics"]
    recorded_at = result["recorded_at"] or datetime.now(timezone.utc)
    date_str = recorded_at.strftime("%Y-%m-%d %H:%M:%S +0000")

    mapping = {
        "weight_kg": ("Body Mass", "kg"),
        "body_fat_pct": ("Body Fat Percentage", "%"),
        "bmi": ("Body Mass Index", "count"),
        "skeletal_muscle_kg": ("Skeletal Muscle Mass", "kg"),
        "bone_mass_kg": ("Bone Mass", "kg"),
        "bmr_kcal": ("Basal Metabolic Rate", "kcal"),
        "visceral_fat_grade": ("Visceral Fat Grade", "count"),
        "body_age": ("Body Age", "count"),
        "body_score": ("Body Score", "count"),
        "subcutaneous_fat_pct": ("Subcutaneous Fat Percentage", "%"),
        "protein_kg": ("Protein Mass", "kg"),
        "body_water_kg": ("Body Water", "kg"),
        "muscle_kg": ("Muscle Mass", "kg"),
        "body_fat_kg": ("Body Fat Mass", "kg"),
        "fat_free_kg": ("Fat Free Body Weight", "kg"),
    }

    if "weight_kg" in metrics and "body_fat_kg" in metrics and "lean_mass_kg" not in metrics:
        metrics["lean_mass_kg"] = round(metrics["weight_kg"] - metrics["body_fat_kg"], 2)
    mapping["lean_mass_kg"] = ("Lean Body Mass", "kg")

    data = [
        {"date": date_str, "qty": metrics[key], "name": name, "units": units}
        for key, (name, units) in mapping.items()
        if key in metrics
    ]
    return {"data": data}
