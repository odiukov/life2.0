"""The legacy orchestrator authenticates through the gateway (sub-project 3c, Task 9)."""

from __future__ import annotations

from uuid import UUID

from fastapi import Header

from gateway.composition import Gateway, build_gateway_from_env

POST_AUTH_HOOKS: list = []  # kept for legacy imports; the gateway registers its own hooks
_gateway: Gateway | None = None


def gateway() -> Gateway:
    global _gateway
    if _gateway is None:
        _gateway = build_gateway_from_env()
    return _gateway


async def current_user(
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> UUID:
    user = await gateway().authenticate(authorization, x_user_id)
    for hook in list(POST_AUTH_HOOKS):
        await hook(user)
    return user
