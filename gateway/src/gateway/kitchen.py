"""/kitchen routes for the app. Every call goes to the kitchen agent's structured skills over A2A."""

from __future__ import annotations

from collections.abc import Callable, Coroutine, Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from household.adapters.http import Authenticate
from pydantic import BaseModel, ValidationError
from shared.ports.skills import SkillCallError, SkillClient, SkillUnavailable
from shared.skill_ids import Kitchen

LocationName = Literal["fridge", "freezer", "pantry"]
ActionName = Literal["consumed", "discarded", "opened", "move", "set_expiry", "set_quantity"]

ERRORS: dict[str, tuple[int, str]] = {
    "item_gone": (409, "item_gone"),
    "already_undone": (409, "already_undone"),
    "conflict": (409, "undo_conflict"),
    "not_found": (404, "undo_not_found"),
    "invalid_params": (422, "invalid_params"),
    "no_household": (404, "no_household"),
}


class Author(BaseModel):
    user_id: UUID
    name: str


class KitchenItem(BaseModel):
    id: UUID
    name: str
    display_name: str
    category: str
    quantity: Decimal
    unit: Literal["pcs", "g", "ml", "pack"]
    location: LocationName
    opened: bool
    opened_on: date | None
    expires_on: date
    expiry_source: Literal["explicit", "estimated", "corrected"]
    added_at: datetime
    added_by: Author | None


class InventoryOut(BaseModel):
    items: list[KitchenItem]


class DigestOut(BaseModel):
    expired: list[KitchenItem]
    today: list[KitchenItem]
    tomorrow: list[KitchenItem]
    soon: list[KitchenItem]


class ItemActionIn(BaseModel):
    action: ActionName
    location: LocationName | None = None
    expires_on: date | None = None
    quantity: Decimal | None = None


class ItemActionOut(BaseModel):
    group_id: UUID
    item: KitchenItem | None


class UndoOut(BaseModel):
    outcome: Literal["done"]


def _decode[OutputT: BaseModel](model: type[OutputT], data: Mapping[str, object]) -> OutputT:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(status_code=502, detail="kitchen_error") from exc


class _KitchenRoute(APIRoute):
    """Use the kitchen error contract for malformed route parameters and bodies."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handle = super().get_route_handler()

        async def kitchen_route(request: Request) -> Response:
            try:
                return await handle(request)
            except RequestValidationError as exc:
                raise HTTPException(status_code=422, detail="invalid_params") from exc

        return kitchen_route


class KitchenGateway:
    def __init__(self, client: SkillClient) -> None:
        self._client = client

    async def _call(
        self, skill_id: str, user: UUID, params: Mapping[str, object]
    ) -> Mapping[str, object]:
        try:
            reply = await self._client.call(skill_id=skill_id, user_id=user, params=params)
        except SkillUnavailable as exc:
            raise HTTPException(status_code=503, detail="kitchen_unavailable") from exc
        except SkillCallError as exc:
            status, detail = ERRORS.get(exc.code, (502, "kitchen_error"))
            raise HTTPException(status_code=status, detail=detail) from exc
        if reply.data is None:
            raise HTTPException(status_code=502, detail="kitchen_error")
        return reply.data

    async def inventory(self, user: UUID, location: LocationName | None) -> InventoryOut:
        params = {"location": location} if location else {}
        return _decode(InventoryOut, await self._call(Kitchen.INVENTORY, user, params))

    async def digest(self, user: UUID) -> DigestOut:
        return _decode(DigestOut, await self._call(Kitchen.DIGEST, user, {}))

    async def act(self, user: UUID, item_id: UUID, body: ItemActionIn) -> ItemActionOut:
        params: dict[str, object] = {"item_id": str(item_id), "action": body.action}
        if body.location is not None:
            params["location"] = body.location
        if body.expires_on is not None:
            params["expires_on"] = body.expires_on.isoformat()
        if body.quantity is not None:
            params["quantity"] = str(body.quantity)
        return _decode(ItemActionOut, await self._call(Kitchen.ITEM_ACTION, user, params))

    async def undo(self, user: UUID, group_id: UUID) -> UndoOut:
        return _decode(UndoOut, await self._call(Kitchen.UNDO, user, {"group_id": str(group_id)}))


def build_router(gateway: KitchenGateway, authenticate: Authenticate) -> APIRouter:
    router = APIRouter(prefix="/kitchen", tags=["kitchen"], route_class=_KitchenRoute)
    user_dependency = Depends(authenticate)

    @router.get("/inventory", response_model=InventoryOut)
    async def inventory(
        location: Annotated[LocationName | None, Query()] = None,
        user: UUID = user_dependency,
    ) -> InventoryOut:
        return await gateway.inventory(user, location)

    @router.get("/digest", response_model=DigestOut)
    async def digest(user: UUID = user_dependency) -> DigestOut:
        return await gateway.digest(user)

    @router.post("/items/{item_id}/action", response_model=ItemActionOut)
    async def act(item_id: UUID, body: ItemActionIn, user: UUID = user_dependency) -> ItemActionOut:
        return await gateway.act(user, item_id, body)

    @router.post("/undo/{group_id}", response_model=UndoOut)
    async def undo(group_id: UUID, user: UUID = user_dependency) -> UndoOut:
        return await gateway.undo(user, group_id)

    return router
