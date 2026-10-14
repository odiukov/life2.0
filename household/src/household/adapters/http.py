"""FastAPI routes for the household. Mounted by the gateway; authentication is injected."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from datetime import datetime, time
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator

from household.application.service import HouseholdChanges, HouseholdService
from household.domain.errors import HouseholdError
from household.domain.model import Household

Authenticate = Callable[..., Awaitable[UUID]]

STATUS: dict[str, int] = {
    "invite_invalid": 404,
    "invite_own": 409,
    "invite_rate_limited": 429,
    "not_owner": 403,
    "household_sole_member": 409,
    "cannot_remove_self": 409,
    "not_member": 404,
    "no_household": 404,
    "invalid_settings": 422,
}


class MemberOut(BaseModel):
    user_id: UUID
    name: str
    role: Literal["owner", "member"]
    joined_at: datetime


class HouseholdOut(BaseModel):
    id: UUID
    name: str
    timezone: str
    digest_time: str = Field(description="HH:MM in the household time zone")
    my_role: Literal["owner", "member"]
    members: list[MemberOut]


class HouseholdPatch(BaseModel):
    name: str | None = None
    timezone: str | None = None
    digest_time: time | None = None

    @field_validator("digest_time", mode="before")
    @classmethod
    def _minute_only(cls, value: object) -> object:
        if value is None:
            return value
        if not isinstance(value, str) or re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value) is None:
            raise HTTPException(status_code=422, detail="invalid_settings")
        return time.fromisoformat(value)


class InviteOut(BaseModel):
    code: str
    expires_at: datetime


class CodeIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)


class PreviewOut(BaseModel):
    household_name: str
    member_count: int
    items_to_move: int


def _out(household: Household, me: UUID) -> HouseholdOut:
    role = household.role_of(me)
    return HouseholdOut(
        id=household.id,
        name=household.name,
        timezone=household.timezone,
        digest_time=household.digest_time.strftime("%H:%M"),
        my_role=role.value if role else "member",
        members=[
            MemberOut(
                user_id=m.user_id, name=m.display_name, role=m.role.value, joined_at=m.joined_at
            )
            for m in household.members
        ],
    )


def _http(error: HouseholdError) -> HTTPException:
    return HTTPException(status_code=STATUS.get(error.code, 400), detail=error.code)


def build_router(service: HouseholdService, authenticate: Authenticate) -> APIRouter:
    router = APIRouter(prefix="/household", tags=["household"])
    user_dependency = Depends(authenticate)

    @router.get("", response_model=HouseholdOut)
    async def get_household(user: UUID = user_dependency) -> HouseholdOut:
        try:
            return _out(await service.get(user), user)
        except HouseholdError as error:
            raise _http(error) from error

    @router.patch("", response_model=HouseholdOut)
    async def patch_household(body: HouseholdPatch, user: UUID = user_dependency) -> HouseholdOut:
        try:
            await service.update(user, HouseholdChanges(body.name, body.timezone, body.digest_time))
            return _out(await service.get(user), user)
        except HouseholdError as error:
            raise _http(error) from error

    @router.post("/invites", response_model=InviteOut)
    async def create_invite(user: UUID = user_dependency) -> InviteOut:
        try:
            created = await service.create_invite(user)
        except HouseholdError as error:
            raise _http(error) from error
        return InviteOut(code=created.code.display, expires_at=created.expires_at)

    @router.post("/join/preview", response_model=PreviewOut)
    async def preview(body: CodeIn, user: UUID = user_dependency) -> PreviewOut:
        try:
            p = await service.preview(user, body.code)
        except HouseholdError as error:
            raise _http(error) from error
        return PreviewOut(
            household_name=p.household_name,
            member_count=p.member_count,
            items_to_move=p.items_to_move,
        )

    @router.post("/join", response_model=HouseholdOut)
    async def join(body: CodeIn, user: UUID = user_dependency) -> HouseholdOut:
        try:
            await service.join(user, body.code)
            return _out(await service.get(user), user)
        except HouseholdError as error:
            raise _http(error) from error

    @router.post("/leave", response_model=HouseholdOut)
    async def leave(user: UUID = user_dependency) -> HouseholdOut:
        try:
            await service.leave(user)
            return _out(await service.get(user), user)
        except HouseholdError as error:
            raise _http(error) from error

    @router.delete("/members/{user_id}", status_code=204)
    async def remove_member(user_id: UUID, user: UUID = user_dependency) -> Response:
        try:
            await service.remove_member(user, user_id)
        except HouseholdError as error:
            raise _http(error) from error
        return Response(status_code=204)

    return router
