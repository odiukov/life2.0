"""Per-user integration credentials sealed with AES-256-GCM."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from shared.adapters.secrets import AesGcmSecretBox, open_json, seal_json
from shared.config import SecretsEnvSettings
from shared.db import get_pool

_box: AesGcmSecretBox | None = None


def _sealer() -> AesGcmSecretBox:
    global _box
    if _box is None:
        _box = AesGcmSecretBox.from_settings(SecretsEnvSettings().secrets)  # type: ignore[call-arg]
    return _box


def _reset_box_for_tests() -> None:
    global _box
    _box = None


def ensure_ready() -> None:
    _sealer()


async def put(user_id: UUID, service: str, payload: dict) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM integrations_credentials WHERE user_id=$1 AND service=$2",
                user_id,
                service,
            )
            await conn.execute(
                "INSERT INTO integrations_credentials (user_id, service, payload_enc) VALUES ($1,$2,$3)",
                user_id,
                service,
                seal_json(_sealer(), payload),
            )


async def get(user_id: UUID, service: str) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT payload_dev, payload_enc FROM integrations_credentials WHERE user_id=$1 AND service=$2",
            user_id,
            service,
        )
        if row is None:
            return None
        await conn.execute(
            "UPDATE integrations_credentials SET last_used_at=now() WHERE user_id=$1 AND service=$2",
            user_id,
            service,
        )
        if row["payload_enc"] is not None:
            return open_json(_sealer(), bytes(row["payload_enc"]))
        if row["payload_dev"] is not None:
            value: Any = row["payload_dev"]
            payload = value if isinstance(value, dict) else json.loads(value)
            await conn.execute(
                "UPDATE integrations_credentials SET payload_enc=$3, payload_dev=NULL "
                "WHERE user_id=$1 AND service=$2 AND payload_enc IS NULL AND payload_dev=$4::jsonb",
                user_id,
                service,
                seal_json(_sealer(), payload),
                value,
            )
            return payload
        return None


async def delete(user_id: UUID, service: str) -> None:
    pool = await get_pool()
    await pool.execute(
        "DELETE FROM integrations_credentials WHERE user_id=$1 AND service=$2",
        user_id,
        service,
    )
