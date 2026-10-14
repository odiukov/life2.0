"""Authenticated inbox and push-token routes for the app."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from household.adapters.http import Authenticate
from pydantic import BaseModel, Field
from shared.ports.clock import Clock
from shared.ports.notifications import NotificationInbox, PushTokens
from shared.ports.uow import UnitOfWorkFactory

TOKEN_PATTERN = r"^Expo(nent)?PushToken\[[^\]]+\]$"


class InboxItemOut(BaseModel):
    id: UUID
    kind: str
    title: str
    body: str
    data: dict[str, str]
    created_at: datetime
    read_at: datetime | None


class InboxPage(BaseModel):
    items: list[InboxItemOut]
    unread_count: int


class ReadAllOut(BaseModel):
    updated: int


class PushTokenIn(BaseModel):
    token: str = Field(pattern=TOKEN_PATTERN, max_length=200)
    platform: Literal["ios", "android"]


def build_router(uow: UnitOfWorkFactory, clock: Clock, authenticate: Authenticate) -> APIRouter:
    router = APIRouter(tags=["notifications"])
    user_dependency = Depends(authenticate)

    @router.get("/notifications", response_model=InboxPage)
    async def page(
        before: Annotated[datetime | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
        user: UUID = user_dependency,
    ) -> InboxPage:
        async with uow.for_user(user) as tx:
            inbox = tx.repo(NotificationInbox)
            items = await inbox.page(user, before=before, limit=limit)
            unread = await inbox.unread_count(user)
        return InboxPage(
            items=[InboxItemOut.model_validate(item, from_attributes=True) for item in items],
            unread_count=unread,
        )

    @router.post("/notifications/read-all", response_model=ReadAllOut)
    async def read_all(user: UUID = user_dependency) -> ReadAllOut:
        async with uow.for_user(user) as tx:
            updated = await tx.repo(NotificationInbox).mark_all_read(user, at=clock.now())
        return ReadAllOut(updated=updated)

    @router.post("/notifications/{notification_id}/read", status_code=204)
    async def read(notification_id: UUID, user: UUID = user_dependency) -> Response:
        async with uow.for_user(user) as tx:
            found = await tx.repo(NotificationInbox).mark_read(
                user, notification_id, at=clock.now()
            )
        if not found:
            raise HTTPException(status_code=404, detail="notification_not_found")
        return Response(status_code=204)

    @router.post("/me/push-tokens", status_code=204)
    async def register(body: PushTokenIn, user: UUID = user_dependency) -> Response:
        async with uow.for_user(user) as tx:
            await tx.repo(PushTokens).upsert(user, body.token, body.platform, at=clock.now())
        return Response(status_code=204)

    @router.delete("/me/push-tokens/{token}", status_code=204)
    async def unregister(token: str, user: UUID = user_dependency) -> Response:
        async with uow.for_user(user) as tx:
            await tx.repo(PushTokens).delete(user, token)
        return Response(status_code=204)

    return router
