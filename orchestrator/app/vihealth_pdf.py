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

    if not metrics:
        return _parse_vihealth_pdf_vision(pdf_bytes)

    return {"recorded_at": recorded_at, "metrics": metrics}


_METRICS_EXTRACTION_PROMPT = """\
This is a ViHealth body composition report.

Extract the following (use null if not visible):
{
  "weight_kg": number (Body composition table, Weight row, first measurement value e.g. 79.6),
  "body_fat_kg": number (Body fat row, first measurement value),
  "body_fat_pct": number (Body fat rate gauge value, e.g. 26.5),
  "bone_mass_kg": number (Bone mass row, first measurement value),
  "protein_kg": number (Protein row, first measurement value),
  "body_water_kg": number (Body water row, first measurement value),
  "muscle_kg": number (Muscle row, first measurement value),
  "skeletal_muscle_kg": number (Skeletal muscle row, first measurement value),
  "bmi": number (BMI gauge value),
  "body_score": number (Body score panel, value out of 100),
  "visceral_fat_grade": number (Other indicators: Visceral fat grade),
  "bmr_kcal": number (Other indicators: Basal metabolic rate, digits only),
  "fat_free_kg": number (Other indicators: Fat-free body weight, digits only),
  "subcutaneous_fat_pct": number (Other indicators: Subcutaneous fat, digits only),
  "body_age": number (Other indicators: Body age),
  "recorded_at": "YYYY-MM-DDTHH:MM:SS" (Measuring time panel)
}

Return ONLY valid JSON, no explanation."""

_METRICS_FLOAT_KEYS = (
    "weight_kg", "body_fat_kg", "body_fat_pct", "bone_mass_kg", "protein_kg",
    "body_water_kg", "muscle_kg", "skeletal_muscle_kg", "bmi", "body_score",
    "visceral_fat_grade", "bmr_kcal", "fat_free_kg", "subcutaneous_fat_pct", "body_age",
)


def _parse_vihealth_pdf_vision(pdf_bytes: bytes) -> dict[str, Any]:
    import base64
    import json as _json
    import os as _os

    import pymupdf
    from langchain_core.messages import HumanMessage
    from shared.llm import build_llm

    provider = _os.environ.get("VIHEALTH_LLM_PROVIDER", "openrouter")
    model = _os.environ.get("VIHEALTH_LLM_MODEL", "mistralai/mistral-small-2603")

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    mat = pymupdf.Matrix(2.0, 2.0)
    pix = page.get_pixmap(matrix=mat)
    b64 = base64.standard_b64encode(pix.tobytes("png")).decode()

    llm = build_llm(provider=provider, model=model)
    response = llm.invoke([
        HumanMessage(content=[
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            {"type": "text", "text": _METRICS_EXTRACTION_PROMPT},
        ])
    ])

    content = response.content
    if isinstance(content, list):
        content = "".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    raw = re.sub(r"^```[a-z]*\n?", "", content.strip())
    raw = re.sub(r"\n?```$", "", raw)

    try:
        extracted: dict = _json.loads(raw)
    except _json.JSONDecodeError:
        return {"recorded_at": None, "metrics": {}}

    metrics: dict[str, Any] = {}
    for key in _METRICS_FLOAT_KEYS:
        val = extracted.get(key)
        if val is not None:
            try:
                metrics[key] = float(val)
            except (TypeError, ValueError):
                pass

    recorded_at: datetime | None = None
    ts_str = extracted.get("recorded_at")
    if ts_str:
        ts = str(ts_str).strip()
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d %b %Y, %H:%M:%S", "%d %b %Y %H:%M:%S"):
            try:
                recorded_at = datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue

    if recorded_at is None:
        # Stable fallback: derive a fixed datetime from the PDF bytes hash
        # so repeated scans of the same file never produce a new DB row.
        import hashlib
        digest = hashlib.sha256(pdf_bytes).digest()
        # Use first 4 bytes as a day offset from epoch (max ~11 000 days ≈ year 2000)
        day_offset = int.from_bytes(digest[:4], "big") % 4000
        from datetime import date, timedelta
        fake_day = date(2000, 1, 1) + timedelta(days=day_offset)
        recorded_at = datetime(fake_day.year, fake_day.month, fake_day.day, tzinfo=timezone.utc)

    return {"recorded_at": recorded_at, "metrics": metrics}


def _extract_profile_from_text(text: str) -> dict[str, Any]:
    """Extract height_cm, weight_kg, age, sex from ViHealth PDF plain text."""
    result: dict[str, Any] = {}

    # Primary: info panel renders as "Male 31 170 cm" on one line
    m = re.search(r"\b(Male|Female)\b\s+(\d{1,3})\s+(\d{2,3})\s*cm", text, re.IGNORECASE)
    if m:
        result["sex"] = m.group(1).lower()
        result["age"] = int(m.group(2))
        result["height_cm"] = float(m.group(3))
    else:
        # Fallback: label and value on separate lines
        sm = re.search(r"(?:Gender|Sex)\b[^\n]*\n\s*(Male|Female)", text, re.IGNORECASE)
        if sm:
            result["sex"] = sm.group(1).lower()
        am = re.search(r"\bAge\b[^\n]*\n\s*(\d{1,3})\b", text, re.IGNORECASE)
        if am:
            result["age"] = int(am.group(1))
        hm = re.search(r"\bHeight\b[^\n]*\n?\s*(\d{2,3})\s*cm", text, re.IGNORECASE)
        if hm:
            result["height_cm"] = float(hm.group(1))

    # Weight from the body composition table: "Weight 79.6(54.1–73.1) ..."
    wm = re.search(r"\bWeight\b[^\n]*?([\d.]+)\s*[\(\[]", text)
    if not wm:
        wm = re.search(r"\bWeight\b[^\n]*\n?\s*([\d.]+)", text)
    if wm:
        result["weight_kg"] = float(wm.group(1))

    return result


def extract_profile_fields(pdf_bytes: bytes) -> dict[str, Any]:
    """Extract demographic profile fields from a ViHealth PDF.

    Tries pdfplumber text extraction first; falls back to vision LLM for
    image-only PDFs (e.g. LePulse exports a raster image with no text layer).
    """
    if pdfplumber is None:
        raise RuntimeError("pdfplumber is not installed")
    import io
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    result = _extract_profile_from_text(text)
    if result:
        return result
    return _extract_profile_fields_vision(pdf_bytes)


_PROFILE_EXTRACTION_PROMPT = """\
This is a ViHealth body composition report from LePulse smart scales.

Extract the following from the report (use null if not visible):
{
  "weight_kg": number (Weight row, first number only — e.g. from "79.6(54.1-73.1)" use 79.6),
  "height_cm": number (from the Name/Gender/Age/Height info panel),
  "age": number (age in years from the info panel),
  "sex": "male" or "female" (gender from the info panel)
}

Return ONLY valid JSON, no explanation."""


def _extract_profile_fields_vision(pdf_bytes: bytes) -> dict[str, Any]:
    """Vision LLM fallback for image-only ViHealth PDFs (no text layer)."""
    import base64
    import json as _json
    import os as _os

    import pymupdf
    from langchain_core.messages import HumanMessage
    from shared.llm import build_llm

    provider = _os.environ.get("VIHEALTH_LLM_PROVIDER", "openrouter")
    model = _os.environ.get("VIHEALTH_LLM_MODEL", "mistralai/mistral-small-2603")

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    mat = pymupdf.Matrix(2.0, 2.0)
    pix = page.get_pixmap(matrix=mat)
    b64 = base64.standard_b64encode(pix.tobytes("png")).decode()

    llm = build_llm(provider=provider, model=model)
    response = llm.invoke([
        HumanMessage(content=[
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            {"type": "text", "text": _PROFILE_EXTRACTION_PROMPT},
        ])
    ])

    content = response.content
    if isinstance(content, list):
        content = "".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    raw = re.sub(r"^```[a-z]*\n?", "", content.strip())
    raw = re.sub(r"\n?```$", "", raw)

    try:
        extracted: dict = _json.loads(raw)
    except _json.JSONDecodeError:
        return {}

    result: dict[str, Any] = {}
    if extracted.get("weight_kg") is not None:
        result["weight_kg"] = float(extracted["weight_kg"])
    if extracted.get("height_cm") is not None:
        result["height_cm"] = float(extracted["height_cm"])
    if extracted.get("age") is not None:
        result["age"] = int(extracted["age"])
    sex = str(extracted.get("sex") or "").lower()
    if sex in ("male", "female"):
        result["sex"] = sex
    return result


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
