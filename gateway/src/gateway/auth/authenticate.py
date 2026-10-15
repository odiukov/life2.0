"""The one FastAPI dependency every app route uses: bearer access tokens, or explicit dev mode."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

import jwt
from fastapi import Header, HTTPException
from shared.observability.logging import get_logger
from shared.ports.uow import UnitOfWorkFactory

from gateway.auth.settings import AuthSettings
from gateway.auth.store import AuthStore
from gateway.auth.tokens import decode_access

Hook = Callable[[UUID], Awaitable[None]]
logger = get_logger(__name__)


class Authenticator:
    def __init__(self, settings: AuthSettings, uow: UnitOfWorkFactory) -> None:
        self._settings = settings
        self._uow = uow
        self._hooks: list[Hook] = []

    def add_hook(self, hook: Hook) -> None:
        self._hooks.append(hook)

    async def __call__(
        self,
        authorization: str | None = Header(default=None),
        x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    ) -> UUID:
        user = (
            await self._dev(x_user_id)
            if self._settings.auth_mode == "dev"
            else await self._bearer(authorization)
        )
        for hook in list(self._hooks):
            try:
                await hook(user)
            except Exception as exc:
                logger.warning("post_auth_hook_failed", error_type=type(exc).__name__)
        return user

    async def _dev(self, header: str | None) -> UUID:
        if not header:
            raise HTTPException(status_code=401, detail="dev_user_required")
        try:
            return UUID(header)
        except ValueError:
            raise HTTPException(status_code=401, detail="dev_user_invalid") from None

    async def _bearer(self, authorization: str | None) -> UUID:
        secret = self._settings.secret()
        if secret is None:
            raise HTTPException(status_code=503, detail="auth_not_configured")
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="missing_bearer_token")
        try:
            user, session = decode_access(authorization.removeprefix("Bearer ").strip(), secret)
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="invalid_token") from None
        if self._settings.session_check:
            async with self._uow.system() as tx:
                if not await tx.repo(AuthStore).active(session, user):
                    raise HTTPException(status_code=401, detail="session_revoked")
        return user
