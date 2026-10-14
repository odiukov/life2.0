"""Structured skills (JSON in, JSON out, no LLM) used by the gateway's /kitchen routes."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID

from shared.a2a.executor import SkillResult
from shared.a2a.request import SkillRequest
from shared.ports.clock import Clock

from kitchen.application.errors import InvalidAction, ItemGone, NoHousehold
from kitchen.application.service import InventoryService, ItemAction, UndoOutcome
from kitchen.domain.model import Batch, Location


class _BadParams(Exception):
    pass


def _fail(code: str) -> SkillResult:
    return SkillResult(output=code, failed=True)


def batch_dto(batch: Batch, members: Mapping[UUID, str]) -> dict[str, object]:
    author = None
    if batch.added_by is not None:
        author = {"user_id": str(batch.added_by), "name": members.get(batch.added_by, "")}
    return {
        "id": str(batch.pk),
        "name": batch.name,
        "display_name": batch.display_name,
        "category": batch.category.value,
        "quantity": str(batch.quantity),
        "unit": batch.unit.value,
        "location": batch.location.value,
        "opened": batch.opened,
        "opened_on": batch.opened_on.isoformat() if batch.opened_on else None,
        "expires_on": batch.expires_on.isoformat(),
        "expiry_source": batch.expiry_source.value,
        "added_at": batch.added_at.isoformat(),
        "added_by": author,
    }


def _param(params: Mapping[str, object], key: str, parse: Callable[[str], object]) -> object | None:
    raw = params.get(key)
    if raw is None:
        return None
    try:
        return parse(str(raw))
    except (ValueError, InvalidOperation) as exc:
        raise _BadParams(key) from exc


class InventorySkill:
    def __init__(self, service: InventoryService) -> None:
        self._service = service

    async def __call__(self, request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        try:
            location = _param(request.params, "location", Location)
            context, active = await self._service.snapshot(request.user_id)
        except _BadParams:
            return _fail("invalid_params")
        except NoHousehold:
            return _fail("no_household")
        items = [
            batch_dto(b, context.members)
            for b in active
            if location is None or b.location is location
        ]
        return SkillResult(output=f"{len(items)} items", data={"items": items})


class DigestSkill:
    def __init__(self, service: InventoryService, clock: Clock) -> None:
        self._service = service
        self._clock = clock

    async def __call__(self, request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        try:
            context, active = await self._service.snapshot(request.user_id)
        except NoHousehold:
            return _fail("no_household")
        today = context.today(self._clock.now())
        buckets: dict[str, list[dict[str, object]]] = {
            "expired": [],
            "today": [],
            "tomorrow": [],
            "soon": [],
        }
        for batch in active:
            days = (batch.expires_on - today).days
            key = (
                "expired"
                if days < 0
                else "today"
                if days == 0
                else "tomorrow"
                if days == 1
                else "soon"
                if days <= 3
                else None
            )
            if key:
                buckets[key].append(batch_dto(batch, context.members))
        return SkillResult(output="digest", data=dict(buckets))


class ItemActionSkill:
    def __init__(self, service: InventoryService) -> None:
        self._service = service

    async def __call__(self, request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        params = request.params
        try:
            item_id = _param(params, "item_id", UUID)
            action = _param(params, "action", ItemAction)
            location = _param(params, "location", Location)
            expires_on = _param(params, "expires_on", date.fromisoformat)
            quantity = _param(params, "quantity", Decimal)
            if not isinstance(item_id, UUID) or not isinstance(action, ItemAction):
                raise _BadParams("item_id/action")
            group_id, batch, context = await self._service.act_with_context(
                request.user_id,
                item_id,
                action,
                location=location if isinstance(location, Location) else None,
                expires_on=expires_on if isinstance(expires_on, date) else None,
                quantity=quantity if isinstance(quantity, Decimal) else None,
            )
        except (_BadParams, InvalidAction):
            return _fail("invalid_params")
        except ItemGone:
            return _fail("item_gone")
        except NoHousehold:
            return _fail("no_household")
        item = batch_dto(batch, context.members) if batch is not None else None
        return SkillResult(output=action.value, data={"group_id": str(group_id), "item": item})


class UndoSkill:
    def __init__(self, service: InventoryService) -> None:
        self._service = service

    async def __call__(self, request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        try:
            group_id = _param(request.params, "group_id", UUID)
            if not isinstance(group_id, UUID):
                raise _BadParams("group_id")
            outcome = await self._service.undo(request.user_id, group_id)
        except _BadParams:
            return _fail("invalid_params")
        except NoHousehold:
            return _fail("no_household")
        if outcome is not UndoOutcome.DONE:
            return _fail(outcome.value)
        return SkillResult(output="done", data={"outcome": "done"})
