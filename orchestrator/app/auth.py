"""Authenticate API requests with local sessions or an explicit local demo user."""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from uuid import UUID

import jwt
from fastapi import Header, HTTPException

from shared.db import get_pool

from .direct_auth import app_secret, decode_access

AUTH_MODE = os.environ.get("AUTH_MODE", "oauth").lower()
POST_AUTH_HOOKS: list[Callable[[UUID], Awaitable[None]]] = []


async def _run_post_auth_hooks(user_id: UUID) -> None:
    for hook in list(POST_AUTH_HOOKS):
        try:
            await hook(user_id)
        except Exception:
            logging.getLogger(__name__).warning("post_auth_hook_failed")


def verify_jwt(authorization: str) -> UUID:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        user_id, _ = decode_access(authorization.removeprefix("Bearer ").strip(), app_secret())
        return user_id
    except jwt.InvalidTokenError as error:
        raise HTTPException(status_code=401, detail="invalid token") from error


async def _session_active(user_id: UUID, sid: UUID) -> bool:
    pool = await get_pool()
    return bool(
        await pool.fetchval(
            "SELECT 1 FROM auth_sessions WHERE id=$1 AND user_id=$2 "
            "AND revoked_at IS NULL AND expires_at>now()",
            sid,
            user_id,
        )
    )


async def current_user(
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> UUID:
    if AUTH_MODE == "dev":
        if not x_user_id:
            raise HTTPException(status_code=401, detail="AUTH_MODE=dev requires X-User-Id header")
        try:
            user_id = UUID(x_user_id)
        except ValueError as error:
            raise HTTPException(status_code=401, detail="X-User-Id is not a valid UUID") from error
    else:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="missing bearer token")
        try:
            user_id, sid = decode_access(
                authorization.removeprefix("Bearer ").strip(), app_secret()
            )
        except jwt.InvalidTokenError as error:
            raise HTTPException(status_code=401, detail="invalid token") from error
        if not await _session_active(user_id, sid):
            raise HTTPException(status_code=401, detail="session expired or revoked")
    await _run_post_auth_hooks(user_id)
    return user_id
