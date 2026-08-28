"""Habit registry CRUD — backed by the `habits` Postgres table.

Canonical name form is lowercase kebab-case single-token (no spaces).
`normalize_name` applies this form to user input.
"""
from __future__ import annotations

import re
from typing import Optional
from uuid import UUID

from shared.db import (
    archive_habit as _db_archive,
    fetch_active_habits,
    insert_habit,
)
from shared.db import get_pool

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_name(raw: str) -> str:
    """Lowercase kebab-case single token. Empty input stays empty."""
    if not raw:
        return ""
    lowered = raw.strip().lower()
    slug = _NON_ALNUM.sub("-", lowered).strip("-")
    return slug


async def list_active(user_id: UUID) -> list[dict]:
    return await fetch_active_habits(user_id)


async def find_by_name(user_id: UUID, raw_name: str) -> Optional[dict]:
    """Look up an active habit by any form of its name (normalized)."""
    target = normalize_name(raw_name)
    if not target:
        return None
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT id::text AS id, name, kind, cadence_type, cadence_days, "
        "target_value, unit, created_at FROM habits "
        "WHERE user_id = $1 AND name = $2 AND archived_at IS NULL",
        user_id, target,
    )
    return dict(row) if row else None


async def create(
    user_id: UUID,
    name: str,
    kind: str,
    cadence_type: str,
    cadence_days: list[str] | None = None,
    target_value: float | None = None,
    unit: str | None = None,
) -> str:
    """Insert a new habit; returns the UUID. Input `name` is normalized first.

    Raises asyncpg.UniqueViolationError on duplicate active name."""
    canonical = normalize_name(name)
    if not canonical:
        raise ValueError("habit name cannot be empty")
    return await insert_habit(
        user_id, name=canonical, kind=kind, cadence_type=cadence_type,
        cadence_days=cadence_days, target_value=target_value, unit=unit,
    )


async def archive(user_id: UUID, habit_id: str) -> bool:
    return await _db_archive(user_id, habit_id)
