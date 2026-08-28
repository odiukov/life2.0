"""Registry CRUD — wraps shared/db.py medication helpers."""
from __future__ import annotations

import re
from typing import Optional
from uuid import UUID

from shared.db import (
    archive_medication as _db_archive,
    fetch_active_medications,
    find_medication_by_name,
    insert_medication,
)

_NON_ALNUM = re.compile(r"[^a-z0-9\u0400-\u04FF]+")  # ASCII + Cyrillic


def normalize_name(raw: str) -> str:
    """Lowercase kebab-case. Preserves Unicode (e.g., Cyrillic). Empty input stays empty."""
    if not raw:
        return ""
    lowered = raw.strip().lower()
    slug = _NON_ALNUM.sub("-", lowered).strip("-")
    return slug


async def list_active(user_id: UUID) -> list[dict]:
    return await fetch_active_medications(user_id)


async def find_by_name(user_id: UUID, raw: str) -> Optional[dict]:
    return await find_medication_by_name(user_id, raw)


async def create(
    user_id: UUID,
    name: str,
    dose: str | None,
    schedule: str,
    notes: str | None = None,
) -> str:
    return await insert_medication(
        user_id, name=name, dose=dose, schedule=schedule, notes=notes,
    )


async def archive(user_id: UUID, med_id: str) -> bool:
    return await _db_archive(user_id, med_id)
