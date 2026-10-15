"""ViHealth / LePulse body-composition reports (text layer). Pure: no PDF library here."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta

_COMPOSITION = {
    "Weight": "weight_kg",
    "Body fat": "body_fat_kg",
    "Bone mass": "bone_mass_kg",
    "Protein": "protein_kg",
    "Body water": "body_water_kg",
    "Muscle": "muscle_kg",
    "Skeletal muscle": "skeletal_muscle_kg",
}
_OTHER = {
    "Visceral fat grade": "visceral_fat_grade",
    "Basal metabolic rate": "bmr_kcal",
    "Fat-free body weight": "fat_free_kg",
    "Subcutaneous fat": "subcutaneous_fat_pct",
    "SMI": "smi",
    "Body age": "body_age",
}
# What a stored body_composition row may contain (the legacy importer's round trip; no "smi").
ROW_KEYS = (
    "weight_kg",
    "body_fat_pct",
    "lean_mass_kg",
    "bmi",
    "skeletal_muscle_kg",
    "bone_mass_kg",
    "bmr_kcal",
    "visceral_fat_grade",
    "body_age",
    "body_score",
    "subcutaneous_fat_pct",
    "protein_kg",
    "body_water_kg",
    "muscle_kg",
    "body_fat_kg",
    "fat_free_kg",
)
_MARKERS = ("Body fat rate", "LePulse", "ViHealth", "Body Mass Index", "Skeletal muscle")
_NUMBER = re.compile(r"^\s*([\d.]+)")


def _number(value: str) -> float | None:
    m = _NUMBER.match(value.replace(",", "."))
    return float(m.group(1)) if m else None


def looks_like_vihealth(text: str) -> bool:
    return any(re.search(marker, text, re.IGNORECASE) for marker in _MARKERS)


def measured_at(text: str) -> datetime | None:
    m = re.search(r"(\d{1,2}\s+\w+\s+\d{4},\s*\d{2}:\d{2}:\d{2})", text)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1).strip(), "%d %b %Y, %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def metrics_from_text(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    if bmi := re.search(r"BMI\D{0,20}?([\d.]+)", text):
        out["bmi"] = float(bmi.group(1))
    if fat := re.search(r"Body fat rate\D{0,30}?([\d.]+)", text):
        out["body_fat_pct"] = float(fat.group(1))
    return out


def metrics_from_tables(tables: Sequence[Sequence[Sequence[str | None]]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for table in tables:
        for row in table:
            if not row or not row[0] or len(row) < 2:
                continue
            label = str(row[0]).strip()
            key = _COMPOSITION.get(label) or _OTHER.get(label)
            if key is not None and (value := _number(str(row[1] or ""))) is not None:
                out[key] = value
    return out


def row_data(metrics: Mapping[str, float]) -> dict[str, float]:
    values = dict(metrics)
    if "weight_kg" in values and "body_fat_kg" in values and "lean_mass_kg" not in values:
        values["lean_mass_kg"] = round(values["weight_kg"] - values["body_fat_kg"], 2)
    return {key: round(float(values[key]), 2) for key in ROW_KEYS if key in values}


def fallback_time(data: bytes) -> datetime:
    """A stable instant with about 58 bits of file identity for undated reports."""
    digest = hashlib.sha256(data).digest()
    offset = int.from_bytes(digest[:4], "big") % 4000
    microseconds = int.from_bytes(digest[4:16], "big") % (86_400 * 1_000_000)
    day = date(2000, 1, 1) + timedelta(days=offset)
    return datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(microseconds=microseconds)


def profile_from_text(text: str) -> dict[str, object]:
    result: dict[str, object] = {}
    m = re.search(r"\b(Male|Female)\b\s+(\d{1,3})\s+(\d{2,3})\s*cm", text, re.IGNORECASE)
    if m:
        result.update(sex=m.group(1).lower(), age=int(m.group(2)), height_cm=float(m.group(3)))
    else:
        if sm := re.search(r"(?:Gender|Sex)\b[^\n]*\n\s*(Male|Female)", text, re.IGNORECASE):
            result["sex"] = sm.group(1).lower()
        if am := re.search(r"\bAge\b[^\n]*\n\s*(\d{1,3})\b", text, re.IGNORECASE):
            result["age"] = int(am.group(1))
        if hm := re.search(r"\bHeight\b[^\n]*\n?\s*(\d{2,3})\s*cm", text, re.IGNORECASE):
            result["height_cm"] = float(hm.group(1))
    wm = re.search(r"\bWeight\b[^\n]*?([\d.]+)\s*[\(\[]", text) or re.search(
        r"\bWeight\b[^\n]*\n?\s*([\d.]+)", text
    )
    if wm:
        result["weight_kg"] = float(wm.group(1))
    return result
