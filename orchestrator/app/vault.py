"""Per-(user, service) credentials vault.

Dual-backend to support cloud-first prod and docker-postgres dev:
  - VAULT_BACKEND=supabase (prod): payload is encrypted via Supabase's
    pgsodium-backed vault.create_secret/vault.decrypted_secrets; the
    integrations_credentials row stores secret_id.
  - VAULT_BACKEND=dev (default local): sealed with SECRETS__KEY (AES-256-GCM), never plaintext.

The schema CHECK constraint enforces exactly-one-of (secret_id, payload_dev, payload_enc),
so every insert must go through one backend cleanly.
"""

from __future__ import annotations

import json
import os
from typing import Any
from uuid import UUID

from shared.adapters.secrets import AesGcmSecretBox, open_json, seal_json
from shared.config import SecretsEnvSettings
from shared.db import get_pool

VAULT_BACKEND = os.environ.get("VAULT_BACKEND", "dev").lower()


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
    """Fail at startup when the dev backend has no usable sealing key."""
    if VAULT_BACKEND != "supabase":
        _sealer()


async def put(user_id: UUID, service: str, payload: dict) -> None:
    """Upsert credentials for (user_id, service). Deletes any prior row+secret."""
    pool = await get_pool()
    async with pool.acquire() as c:
        async with c.transaction():
            prior = await c.fetchrow(
                "SELECT secret_id FROM integrations_credentials WHERE user_id=$1 AND service=$2",
                user_id,
                service,
            )
            if prior is not None:
                if prior["secret_id"] is not None:
                    # Delete the encrypted secret in the vault too
                    await c.execute(
                        "SELECT vault.delete_secret($1)",
                        prior["secret_id"],
                    )
                await c.execute(
                    "DELETE FROM integrations_credentials WHERE user_id=$1 AND service=$2",
                    user_id,
                    service,
                )
            if VAULT_BACKEND == "supabase":
                payload_str = json.dumps(payload)
                secret_id = await c.fetchval(
                    "SELECT vault.create_secret($1, $2, $3)",
                    payload_str,
                    f"{user_id}:{service}",
                    f"{service} credentials for {user_id}",
                )
                await c.execute(
                    "INSERT INTO integrations_credentials "
                    "(user_id, service, secret_id) VALUES ($1, $2, $3)",
                    user_id,
                    service,
                    secret_id,
                )
            else:
                await c.execute(
                    "INSERT INTO integrations_credentials "
                    "(user_id, service, payload_enc) VALUES ($1, $2, $3)",
                    user_id,
                    service,
                    seal_json(_sealer(), payload),
                )


async def get(user_id: UUID, service: str) -> dict | None:
    """Return decrypted payload, or None if not connected."""
    pool = await get_pool()
    async with pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT secret_id, payload_dev, payload_enc FROM integrations_credentials "
            "WHERE user_id=$1 AND service=$2",
            user_id,
            service,
        )
        if row is None:
            return None
        # Touch last_used_at for observability
        await c.execute(
            "UPDATE integrations_credentials SET last_used_at=now() "
            "WHERE user_id=$1 AND service=$2",
            user_id,
            service,
        )
        if row["payload_enc"] is not None:
            return open_json(_sealer(), bytes(row["payload_enc"]))
        if row["payload_dev"] is not None:
            val: Any = row["payload_dev"]
            payload = val if isinstance(val, dict) else json.loads(val)
            await c.execute(
                "UPDATE integrations_credentials SET payload_enc=$3, payload_dev=NULL "
                "WHERE user_id=$1 AND service=$2 AND payload_enc IS NULL "
                "AND payload_dev=$4::jsonb",
                user_id,
                service,
                seal_json(_sealer(), payload),
                val,
            )
            return payload
        # Supabase vault path
        decrypted = await c.fetchval(
            "SELECT decrypted_secret FROM vault.decrypted_secrets WHERE id=$1",
            row["secret_id"],
        )
        return json.loads(decrypted) if decrypted else None


async def delete(user_id: UUID, service: str) -> None:
    """Remove credentials + any Supabase-vault secret for (user_id, service)."""
    pool = await get_pool()
    async with pool.acquire() as c:
        async with c.transaction():
            row = await c.fetchrow(
                "SELECT secret_id FROM integrations_credentials WHERE user_id=$1 AND service=$2",
                user_id,
                service,
            )
            if row is None:
                return
            if row["secret_id"] is not None:
                await c.execute("SELECT vault.delete_secret($1)", row["secret_id"])
            await c.execute(
                "DELETE FROM integrations_credentials WHERE user_id=$1 AND service=$2",
                user_id,
                service,
            )
