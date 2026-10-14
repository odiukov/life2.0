"""CredentialStore over integrations_credentials; payloads sealed in payload_enc, never plaintext."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from hashlib import sha256
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, null, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.adapters.secrets import open_json, seal_json
from shared.ports.credentials import CredentialsUnreadable
from shared.ports.secrets import SecretBox, SecretsUnreadable
from shared.schema.tables import integrations_credentials as creds


class SqlCredentialStore:
    def __init__(self, conn: AsyncConnection, box: SecretBox) -> None:
        self._conn = conn
        self._box = box

    async def get(self, user_id: UUID, service: str) -> dict[str, Any] | None:
        row = (
            await self._conn.execute(
                select(creds.c.payload_dev, creds.c.payload_enc, creds.c.secret_id)
                .where(creds.c.user_id == user_id, creds.c.service == service)
                .with_for_update()
            )
        ).one_or_none()
        if row is None:
            return None
        if row.payload_enc is not None:
            try:
                payload = open_json(self._box, bytes(row.payload_enc))
            except SecretsUnreadable as exc:
                raise CredentialsUnreadable(service) from exc
        elif row.payload_dev is not None:
            payload = dict(row.payload_dev)
            await self._write(user_id, service, payload)  # re-seal legacy plaintext in place
        else:
            raise CredentialsUnreadable(
                service
            )  # Supabase Vault rows are read by the orchestrator only
        await self._conn.execute(
            update(creds)
            .where(creds.c.user_id == user_id, creds.c.service == service)
            .values(last_used_at=datetime.now(UTC))
        )
        return payload

    async def revision(self, user_id: UUID, service: str) -> str | None:
        row = (
            await self._conn.execute(
                select(creds.c.payload_enc)
                .where(creds.c.user_id == user_id, creds.c.service == service)
                .with_for_update()
            )
        ).one_or_none()
        if row is None or row.payload_enc is None:
            return None
        # A fresh random nonce makes even identical replacements a new generation.
        return sha256(bytes(row.payload_enc)).hexdigest()

    async def _write(self, user_id: UUID, service: str, payload: Mapping[str, Any]) -> None:
        sealed = seal_json(self._box, dict(payload))
        statement = insert(creds).values(
            user_id=user_id, service=service, payload_enc=sealed, payload_dev=null(), secret_id=None
        )
        await self._conn.execute(
            statement.on_conflict_do_update(
                index_elements=[creds.c.user_id, creds.c.service],
                set_={"payload_enc": sealed, "payload_dev": null(), "secret_id": None},
            )
        )

    async def put(self, user_id: UUID, service: str, payload: Mapping[str, Any]) -> None:
        await self._write(user_id, service, payload)

    async def merge(self, user_id: UUID, service: str, changes: Mapping[str, Any]) -> None:
        current = await self.get(user_id, service)
        if current is not None:
            await self._write(user_id, service, {**current, **changes})

    async def delete(self, user_id: UUID, service: str) -> None:
        await self._conn.execute(
            delete(creds).where(creds.c.user_id == user_id, creds.c.service == service)
        )


def sql_credential_store(box: SecretBox) -> Callable[[AsyncConnection], SqlCredentialStore]:
    def factory(conn: AsyncConnection) -> SqlCredentialStore:
        return SqlCredentialStore(conn, box)

    return factory
