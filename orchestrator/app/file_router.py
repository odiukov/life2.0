from __future__ import annotations

import re
from typing import Literal
from uuid import UUID

FileType = Literal["vihealth", "payoneer", "unknown"]

_VIHEALTH_PATTERNS = [
    r"Body fat rate",
    r"LePulse",
    r"ViHealth",
    r"Body Mass Index",
    r"Skeletal muscle",
]

_PAYONEER_PATTERNS = [
    r"Payoneer",
    r"Account Statement",
]


def _classify_text(text: str) -> FileType:
    for pattern in _VIHEALTH_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return "vihealth"
    payoneer_hits = sum(
        1 for p in _PAYONEER_PATTERNS if re.search(p, text, re.IGNORECASE)
    )
    if payoneer_hits >= 2:
        return "payoneer"
    return "unknown"


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    import pdfplumber
    import io
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


_VIHEALTH_FILENAMES = ["lescale", "vihealth", "lepulse"]
_PAYONEER_FILENAMES = ["payoneer"]


def detect_file_type(pdf_bytes: bytes, filename: str | None = None) -> FileType:
    if filename:
        name = filename.lower()
        if any(k in name for k in _VIHEALTH_FILENAMES):
            return "vihealth"
        if any(k in name for k in _PAYONEER_FILENAMES):
            return "payoneer"
    text = _extract_pdf_text(pdf_bytes)
    return _classify_text(text)


_METRIC_MAP: dict[str, str] = {
    "Body Mass": "weight_kg",
    "Body Fat Percentage": "body_fat_pct",
    "Lean Body Mass": "lean_mass_kg",
    "Body Mass Index": "bmi",
    "Skeletal Muscle Mass": "skeletal_muscle_kg",
    "Bone Mass": "bone_mass_kg",
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


def _map_body_rows(payload: dict) -> list[dict]:
    from datetime import datetime, timezone

    by_date: dict[str, dict] = {}
    by_date_dt: dict[str, datetime] = {}

    for entry in payload.get("data", []):
        name = entry.get("name", "")
        key = _METRIC_MAP.get(name)
        if not key:
            continue
        date_str = entry.get("date", "")
        if not date_str:
            continue
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S %z").astimezone(timezone.utc)
        day = dt.date().isoformat()
        if day not in by_date:
            by_date[day] = {}
            by_date_dt[day] = dt
        val = entry.get("qty")
        if val is not None:
            by_date[day][key] = round(float(val), 2)

    return [
        {
            "agent": "body",
            "type": "body_composition",
            "data": metrics,
            "recorded_at": by_date_dt[day],
            "source": "vihealth",
        }
        for day, metrics in by_date.items()
        if metrics
    ]


def _vihealth_summary(rows: list[dict], written: int, unchanged: int) -> str:
    if not rows:
        return "PDF не содержит данных измерений."
    if written == 0:
        # All rows already existed — show last measurement without implying new import
        last = sorted(rows, key=lambda r: r["recorded_at"])[-1]
        m = last["data"]
        parts = []
        if "weight_kg" in m:
            parts.append(f"Вес: {m['weight_kg']} кг")
        if "body_fat_pct" in m:
            parts.append(f"жир: {m['body_fat_pct']}%")
        if "bmi" in m:
            parts.append(f"ИМТ: {m['bmi']}")
        detail = (", ".join(parts) + ".") if parts else ""
        return f"Данные уже в базе (пропущено: {unchanged}). Последнее измерение: {detail}"
    n = written
    last_digit, tens = n % 10, n % 100
    suffix = "е" if last_digit == 1 and tens != 11 else "я" if last_digit in (2, 3, 4) and tens not in (12, 13, 14) else "й"
    lines = [f"Импортировал {n} измерени{suffix} (без изменений: {unchanged})."]
    last = sorted(rows, key=lambda r: r["recorded_at"])[-1]
    m = last["data"]
    parts = []
    if "weight_kg" in m:
        parts.append(f"Вес: {m['weight_kg']} кг")
    if "body_fat_pct" in m:
        parts.append(f"жир: {m['body_fat_pct']}%")
    if "bmi" in m:
        parts.append(f"ИМТ: {m['bmi']}")
    if parts:
        lines.append(", ".join(parts) + ".")
    return "\n".join(lines)


async def route_file(
    pdf_bytes: bytes,
    user_id: UUID,
    agent_hint: str | None,
    filename: str | None = None,
) -> str:
    resolved: FileType
    if agent_hint in ("body", "vihealth"):
        resolved = "vihealth"
    elif agent_hint in ("finance", "payoneer"):
        resolved = "payoneer"
    else:
        resolved = detect_file_type(pdf_bytes, filename)

    if resolved == "vihealth":
        return await _ingest_vihealth(pdf_bytes, user_id)
    elif resolved == "payoneer":
        return await _ingest_payoneer(pdf_bytes, user_id)
    return (
        "Не удалось определить тип файла. "
        "Укажи /body или /finance перед отправкой."
    )


async def _ingest_vihealth(pdf_bytes: bytes, user_id: UUID) -> str:
    from .vihealth_pdf import build_payload_from_pdf, extract_profile_fields
    from .db import insert_body_rows
    from shared.db import save_body_profile

    payload = build_payload_from_pdf(pdf_bytes)
    rows = _map_body_rows(payload)
    written, unchanged = await insert_body_rows(rows, user_id)

    profile = extract_profile_fields(pdf_bytes)
    profile_keys = {"height_cm", "age", "sex"}
    profile_updates = {k: v for k, v in profile.items() if k in profile_keys}
    if profile_updates:
        await save_body_profile(user_id, profile_updates)

    return _vihealth_summary(rows, written, unchanged)


async def _ingest_payoneer(pdf_bytes: bytes, user_id: UUID) -> str:
    from .payoneer_pdf import parse_payoneer_pdf, PayoneerPdfFormatError
    from .finance_ingest import ingest_rows, categorize_new, build_upload_summary
    from .finance_queries import income_for_month, spending_by_category
    from decimal import Decimal

    try:
        rows, parse_skipped = parse_payoneer_pdf(pdf_bytes)
    except PayoneerPdfFormatError as e:
        return f"Не удалось прочитать Payoneer PDF: {e}"

    if not rows:
        return f"PDF не содержит транзакций (пропущено при парсинге: {parse_skipped})."

    ingest_result = await ingest_rows(user_id, rows)
    await categorize_new(user_id, ingest_result["uncategorized_ids"])

    months = sorted({r["ts"].strftime("%Y-%m") for r in rows}) or [""]
    income_total: dict[str, Decimal] = {}
    spending_total: dict[str, Decimal] = {}
    top_categories: list[tuple[str, Decimal, str]] = []
    for m in months:
        inc = await income_for_month(user_id, m)
        for cur, amt in inc.items():
            income_total[cur] = income_total.get(cur, Decimal("0")) + amt
        spend = await spending_by_category(user_id, m)
        for cat, cur, amt in spend:
            spending_total[cur] = spending_total.get(cur, Decimal("0")) + amt
            top_categories.append((cat, amt, cur))
    top_categories.sort(key=lambda t: t[1], reverse=True)

    return build_upload_summary(
        inserted=ingest_result["inserted"],
        skipped=ingest_result["skipped"] + parse_skipped,
        income_by_currency=income_total,
        spending_by_currency=spending_total,
        top_categories=top_categories[:3],
    )
