"""/me/profile: the body profile the nutrition agent's goals use, and the ViHealth form import."""

from __future__ import annotations

from collections.abc import Callable, Coroutine, Mapping
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from household.adapters.http import Authenticate
from pydantic import BaseModel, ConfigDict, Field
from shared.domain.energy import ActivityLevel, Sex, bmr_mifflin_st_jeor, tdee
from shared.ports.health_logs import HealthLogRepository
from shared.ports.profile import BodyProfileRepository
from shared.ports.skills import Attachment, SkillCallError, SkillClient, SkillUnavailable
from shared.ports.uow import UnitOfWorkFactory
from shared.skill_ids import Body
from starlette.types import Message

from gateway.validation import PrivateInputRoute

SexName = Literal["male", "female"]
Activity = Literal["sedentary", "light", "moderate", "active", "very_active"]
_IMPORT_ERRORS = {
    "not_a_report": 422,
    "unreadable_pdf": 422,
    "invalid_params": 422,
    "vision_unavailable": 503,
}


class BodyProfileOut(BaseModel):
    height_cm: float | None = None
    weight_kg: float | None = None
    age: int | None = None
    sex: SexName | None = None
    activity_level: Activity | None = None
    calorie_goal_override: int | None = None
    tdee_kcal: int | None = None


class BodyProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    height_cm: float | None = Field(default=None, ge=50, le=260)
    weight_kg: float | None = Field(default=None, ge=20, le=400)
    age: int | None = Field(default=None, ge=1, le=120)
    sex: SexName | None = None
    activity_level: Activity | None = None
    calorie_goal_override: int | None = Field(default=None, ge=800, le=8000)


class ViHealthProfileImport(BaseModel):
    height_cm: float | None = None
    weight_kg: float | None = None
    age: int | None = None
    sex: SexName | None = None


def _profile_out(stored: dict[str, object]) -> BodyProfileOut:
    """An old row with a bad value reads as None for that field instead of failing the request."""
    clean: dict[str, object] = {}
    for key in BodyProfileOut.model_fields:
        if key in stored:
            try:
                BodyProfileOut.model_validate({key: stored[key]})
            except ValueError:
                continue
            clean[key] = stored[key]
    return BodyProfileOut.model_validate(clean)


def build_router(
    uow: UnitOfWorkFactory, body: SkillClient, authenticate: Authenticate, *, max_bytes: int
) -> APIRouter:
    # Bound the multipart stream before parsing/spooling; allow a small header envelope.
    body_cap = max_bytes + 65_536

    class LimitedUploadRoute(PrivateInputRoute):
        def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
            handle = super().get_route_handler()
            if self.path != "/me/profile/import-pdf":
                return handle

            async def limited_upload(request: Request) -> Response:
                length = request.headers.get("content-length")
                if (
                    length is not None
                    and length.isdecimal()
                    and (len(length) > 20 or int(length) > body_cap)
                ):
                    raise HTTPException(status_code=413, detail="file_too_large")

                received = 0

                async def limited_receive() -> Message:
                    nonlocal received
                    message = await request.receive()
                    if message["type"] == "http.request":
                        received += len(message.get("body", b""))
                        if received > body_cap:
                            raise HTTPException(status_code=413, detail="file_too_large")
                    return message

                return await handle(Request(request.scope, receive=limited_receive))

            return limited_upload

    router = APIRouter(tags=["profile"], route_class=LimitedUploadRoute)
    user_dependency = Depends(authenticate)

    @router.get("/me/profile", response_model=BodyProfileOut)
    async def get_profile(user: UUID = user_dependency) -> BodyProfileOut:
        async with uow.for_user(user) as tx:
            profile = await tx.repo(BodyProfileRepository).get(user)
            weight = profile.get("weight_kg")
            if weight is None:
                latest = await tx.repo(HealthLogRepository).recent(
                    user, types=["body_composition"], limit=1, agent="body"
                )
                weight = latest[0].data.get("weight_kg") if latest else None
        out = _profile_out({**profile, "weight_kg": weight})
        if out.height_cm and out.weight_kg and out.age and out.sex and out.activity_level:
            bmr = bmr_mifflin_st_jeor(
                weight_kg=out.weight_kg, height_cm=out.height_cm, age=out.age, sex=Sex(out.sex)
            )
            out.tdee_kcal = tdee(bmr, ActivityLevel(out.activity_level))
        return out

    @router.patch("/me/profile")
    async def update_profile(
        body_in: BodyProfileUpdate, user: UUID = user_dependency
    ) -> dict[str, bool]:
        async with uow.for_user(user) as tx:
            await tx.repo(BodyProfileRepository).update(
                user, body_in.model_dump(exclude_unset=True)
            )
        return {"ok": True}

    @router.post("/me/profile/import-pdf", response_model=ViHealthProfileImport)
    async def import_pdf(
        file: Annotated[UploadFile, File()], user: UUID = user_dependency
    ) -> ViHealthProfileImport:
        data = await file.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise HTTPException(status_code=413, detail="file_too_large")
        if not data.startswith(b"%PDF-"):
            raise HTTPException(status_code=415, detail="expected_pdf")
        try:
            reply = await body.call(
                skill_id=Body.IMPORT_VIHEALTH,
                user_id=user,
                params={"save_profile": False},
                attachments=[
                    Attachment(
                        name=file.filename or "report.pdf", mime="application/pdf", data=data
                    )
                ],
            )
        except SkillUnavailable:
            raise HTTPException(status_code=503, detail="body_unavailable") from None
        except SkillCallError as exc:
            raise HTTPException(
                status_code=_IMPORT_ERRORS.get(exc.code, 502), detail=exc.code
            ) from None
        fields = (reply.data or {}).get("profile_fields") or {}
        if not isinstance(fields, Mapping):
            raise HTTPException(status_code=502, detail="body_invalid_reply")
        return ViHealthProfileImport.model_validate(
            {k: fields.get(k) for k in ("height_cm", "weight_kg", "age", "sex")}
        )

    return router
