from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from shared.config import DatabaseSettings


def _dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def create_engine(settings: DatabaseSettings) -> AsyncEngine:
    return create_async_engine(
        settings.dsn.get_secret_value(),
        pool_size=settings.pool_size,
        pool_pre_ping=True,
        json_serializer=_dumps,
    )
