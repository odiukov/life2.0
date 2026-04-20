"""Resolve per-user consent flag from Postgres with in-memory TTL cache."""
from __future__ import annotations

import time
from typing import Tuple

from shared.db import get_pool

_CACHE: dict[str, Tuple[bool, float]] = {}
_TTL_SECONDS = 300


async def is_consented(user_id: str) -> bool:
    """Return True iff user has opted in to body-capture. Cache TTL: 5 min."""
    now = time.time()
    hit = _CACHE.get(user_id)
    if hit is not None and (now - hit[1]) < _TTL_SECONDS:
        return hit[0]
    pool = await get_pool()
    row = await pool.fetchval(
        "SELECT bodies_ok FROM telemetry_consent WHERE user_id = $1",
        user_id,
    )
    consented = bool(row) if row is not None else False
    _CACHE[user_id] = (consented, now)
    return consented


def clear_cache() -> None:
    """Testing + admin utility."""
    _CACHE.clear()
