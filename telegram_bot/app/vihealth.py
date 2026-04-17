"""Parse ViHealth PDF reports using Claude Vision.

Pipeline:
  PDF bytes → render first page to PNG (pymupdf) → Claude Vision extraction → dict payload
"""

import base64
import json
import os
import re
from datetime import datetime, timezone
from typing import Any

import pymupdf
from langchain_core.messages import HumanMessage

from shared.llm import build_llm


_VISION_PROVIDER = os.environ.get("VIHEALTH_LLM_PROVIDER", "anthropic")
_VISION_MODEL = os.environ.get("VIHEALTH_LLM_MODEL", "claude-haiku-4-5-20251001")


_EXTRACTION_PROMPT = """\
This is a ViHealth body composition report from LePulse smart scales.

Extract ALL of the following values as a JSON object (use null if not present):
{
  "recorded_at": "datetime from Measuring time field in format YYYY-MM-DDTHH:MM:SS (e.g. 2026-04-14T09:37:16)",
  "weight_kg": number,
  "body_fat_kg": number,
  "body_fat_pct": number,
  "bone_mass_kg": number,
  "protein_kg": number,
  "body_water_kg": number,
  "muscle_kg": number,
  "skeletal_muscle_kg": number,
  "bmi": number,
  "visceral_fat_grade": number,
  "bmr_kcal": number,
  "fat_free_kg": number,
  "subcutaneous_fat_pct": number,
  "body_age": number,
  "body_score": number
}

For measurement columns like "79.6(54.1–73.1)", use only the first number (79.6).
Return ONLY valid JSON, no explanation."""


def _render_pdf_to_png(pdf_bytes: bytes) -> bytes:
    """Render the first page of a PDF to PNG bytes."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    mat = pymupdf.Matrix(2.0, 2.0)  # 2x scale for better OCR quality
    pix = page.get_pixmap(matrix=mat)
    return pix.tobytes("png")


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d %b %Y, %H:%M:%S",
        "%d %b %Y %H:%M:%S",
        "%B %d, %Y %H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # Last resort: try dateutil if available
    try:
        from dateutil import parser as dateutil_parser
        return dateutil_parser.parse(value).replace(tzinfo=timezone.utc)
    except Exception:
        pass
    return None


def parse_vihealth_pdf_vision(pdf_bytes: bytes) -> dict[str, Any]:
    """Use a vision-capable LLM to extract body composition metrics from a ViHealth PDF.

    Provider/model come from VIHEALTH_LLM_PROVIDER / VIHEALTH_LLM_MODEL
    (defaults: anthropic + claude-haiku-4-5-20251001), so the PDF path stays
    on a cheap vision model even when the rest of the stack runs on a
    different LLM_PROVIDER.

    Returns:
        { "recorded_at": datetime|None, "metrics": { key: float, ... } }
    """
    png_bytes = _render_pdf_to_png(pdf_bytes)
    b64_image = base64.standard_b64encode(png_bytes).decode()

    llm = build_llm(provider=_VISION_PROVIDER, model=_VISION_MODEL)
    response = llm.invoke([
        HumanMessage(content=[
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64_image}"},
            },
            {"type": "text", "text": _EXTRACTION_PROMPT},
        ])
    ])

    content = response.content
    if isinstance(content, list):
        content = "".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    raw = content.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    extracted: dict = json.loads(raw)

    recorded_at = _parse_datetime(extracted.pop("recorded_at", None))

    metrics = {k: float(v) for k, v in extracted.items() if v is not None}

    return {"recorded_at": recorded_at, "metrics": metrics}


def build_sync_payload(pdf_bytes: bytes) -> dict[str, Any]:
    """Convert ViHealth PDF to the apple_health payload format for /sync/body."""
    result = parse_vihealth_pdf_vision(pdf_bytes)
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
