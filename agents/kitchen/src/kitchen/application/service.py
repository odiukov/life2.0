"""Inventory use cases. Each public method is one transaction."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from shared.ports.clock import Clock
from shared.ports.uow import UnitOfWork, UnitOfWorkFactory

from kitchen.application.errors import InvalidAction, ItemGone, NoHousehold
from kitchen.application.ports import (
    BatchRepository,
    HouseholdContext,
    HouseholdView,
    LoggedChange,
    OperationGroup,
    OperationLog,
)
from kitchen.application.schema import OperationList
from kitchen.domain.model import Batch, ExpirySource, Location, Source, Status
from kitchen.domain.rules import (
    Change,
    IncompatibleUnits,
    NewBatch,
    add_batch,
    consume,
    discard,
    normalize_name,
    set_expiry,
    set_quantity,
    update_batch,
)
from kitchen.domain.snapshot import from_snapshot, to_snapshot
from kitchen.domain.units import normalize_quantity

APP_SOURCE = "app"


class ItemAction(StrEnum):
    CONSUMED = "consumed"
    DISCARDED = "discarded"
    OPENED = "opened"
    MOVE = "move"
    SET_EXPIRY = "set_expiry"
    SET_QUANTITY = "set_quantity"


class UndoOutcome(StrEnum):
    DONE = "done"
    ALREADY_UNDONE = "already_undone"
    CONFLICT = "conflict"
    NOT_FOUND = "not_found"


class ApplyNeedsClarification(Exception):
    """Nothing was applied; the reference needs the user's answer before retrying."""

    def __init__(self, *, ref: str, reason: str, candidates: tuple[str, ...] = ()) -> None:
        super().__init__(reason)
        self.ref = ref
        self.reason = reason
        self.candidates = candidates


@dataclass(frozen=True, slots=True)
class AppliedChange:
    op_type: str
    before: Batch | None
    after: Batch


@dataclass(slots=True)
class ApplyResult:
    group_id: UUID
    changes: list[AppliedChange] = field(default_factory=list)
    not_found: list[str] = field(default_factory=list)

    def by_type(self, op_type: str) -> list[AppliedChange]:
        return [c for c in self.changes if c.op_type == op_type]


async def _context(uow: UnitOfWork, user_id: UUID) -> HouseholdContext:
    context = await uow.repo(HouseholdView).current()
    if context is None or user_id not in context.members:
        raise NoHousehold
    return context


async def _locked_context(uow: UnitOfWork, user_id: UUID) -> HouseholdContext:
    """Lock the captured household, then authorize using a fresh membership read.

    BatchRepository.lock must use the same household lock as membership mutation;
    SQL adapters call public.household_lock(uuid) and retain it until UoW exit.
    Reject a moved actor rather than reading or writing through the old scope.
    """
    expected = await _context(uow, user_id)
    await uow.repo(BatchRepository).lock()
    current = await _context(uow, user_id)
    if current.household_id != expected.household_id:
        raise NoHousehold
    return current


def _logged(change: AppliedChange) -> LoggedChange:
    return LoggedChange(
        op_type=change.op_type,
        batch_id=change.after.pk,
        before=to_snapshot(change.before) if change.before else None,
        after=to_snapshot(change.after),
    )


class InventoryService:
    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    async def context(self, user_id: UUID) -> HouseholdContext:
        async with self._uow.for_user(user_id) as uow:
            return await _locked_context(uow, user_id)

    async def snapshot(self, user_id: UUID) -> tuple[HouseholdContext, list[Batch]]:
        async with self._uow.for_user(user_id) as uow:
            context = await _locked_context(uow, user_id)
            return context, await uow.repo(BatchRepository).list_active()

    async def apply(
        self,
        user_id: UUID,
        *,
        ops: OperationList,
        refs: Mapping[str, str],
        source: Source,
    ) -> ApplyResult:
        """Commit valid operations, skip missing refs; clarification aborts all changes."""
        now = self._clock.now()
        result = ApplyResult(group_id=uuid4())
        async with self._uow.for_user(user_id) as uow:
            context = await _locked_context(uow, user_id)
            today = context.today(now)
            repo = uow.repo(BatchRepository)
            active = {b.pk: b for b in await repo.list_active()}

            def named(ref: str) -> list[Batch]:
                name = normalize_name(refs[ref]) if ref in refs else None
                batches = [b for b in active.values() if name and b.name == name]
                if not batches and ref not in result.not_found:
                    result.not_found.append(ref)
                return batches

            async def persist(change: Change) -> None:
                if change.before is None:
                    saved = await repo.add(change.after, group_id=result.group_id)
                else:
                    await repo.save(change.after, group_id=result.group_id)
                    saved = change.after
                if saved.status is Status.ACTIVE:
                    active[saved.pk] = saved
                else:
                    active.pop(saved.pk, None)
                result.changes.append(AppliedChange(change.op_type, change.before, saved))

            for item in ops.adds:
                try:
                    quantity, unit = normalize_quantity(Decimal(str(item.quantity)), item.unit)
                except ValueError as error:
                    raise ApplyNeedsClarification(
                        ref=item.name, reason="invalid_quantity"
                    ) from error
                new = NewBatch(
                    name=normalize_name(item.name),
                    display_name=item.display_name.strip() or item.name,
                    category=item.category,
                    quantity=quantity,
                    unit=unit,
                    location=item.location,
                    opened=item.opened,
                    expires_on=item.expires_on,
                    shelf_life_days=item.shelf_life_days,
                    opened_shelf_life_days=item.opened_shelf_life_days,
                    source=source,
                    added_by=user_id,
                )
                await persist(add_batch(list(active.values()), new, today=today, now=now))
            for upd in ops.updates:
                batches = named(upd.item_ref)
                if not batches:
                    continue
                await persist(
                    update_batch(
                        batches,
                        opened=upd.opened,
                        location=upd.location,
                        expires_on=upd.expires_on,
                        opened_shelf_life_days=upd.opened_shelf_life_days,
                        today=today,
                    )
                )
            for con in ops.consumes:
                batches = named(con.item_ref)
                if not batches:
                    continue
                amount = Decimal(str(con.quantity)) if con.quantity is not None else None
                try:
                    changes = consume(batches, quantity=amount, unit=con.unit)
                except IncompatibleUnits as error:
                    raise ApplyNeedsClarification(
                        ref=con.item_ref,
                        reason="incompatible_units",
                        candidates=tuple(sorted({b.unit.value for b in batches})),
                    ) from error
                except ValueError as error:
                    raise ApplyNeedsClarification(
                        ref=con.item_ref, reason="invalid_quantity"
                    ) from error
                for change in changes:
                    await persist(change)
            for dis in ops.discards:
                batches = named(dis.item_ref)
                if not batches:
                    continue
                await persist(discard(batches))
            if result.changes:
                await uow.repo(OperationLog).add(
                    OperationGroup(
                        id=result.group_id,
                        user_id=user_id,
                        created_at=now,
                        source=source.value,
                        changes=tuple(_logged(c) for c in result.changes),
                    )
                )
        return result

    async def act(
        self,
        user_id: UUID,
        batch_id: UUID,
        action: ItemAction,
        *,
        location: Location | None = None,
        expires_on: date | None = None,
        quantity: Decimal | None = None,
    ) -> tuple[UUID, Batch | None]:
        now = self._clock.now()
        group_id = uuid4()
        async with self._uow.for_user(user_id) as uow:
            context = await _locked_context(uow, user_id)
            today = context.today(now)
            repo = uow.repo(BatchRepository)
            batch = await repo.get(batch_id)
            if batch is None or batch.status is not Status.ACTIVE:
                raise ItemGone
            match action:
                case ItemAction.CONSUMED:
                    change = consume([batch], quantity=None, unit=None)[0]
                case ItemAction.DISCARDED:
                    change = discard([batch])
                case ItemAction.OPENED:
                    change = update_batch(
                        [batch],
                        opened=True,
                        location=None,
                        expires_on=None,
                        opened_shelf_life_days=None,
                        today=today,
                    )
                case ItemAction.MOVE:
                    if location is None:
                        raise InvalidAction("location")
                    change = update_batch(
                        [batch],
                        opened=None,
                        location=location,
                        expires_on=None,
                        opened_shelf_life_days=None,
                        today=today,
                    )
                case ItemAction.SET_EXPIRY:
                    if expires_on is None:
                        raise InvalidAction("expires_on")
                    change = set_expiry(batch, expires_on, ExpirySource.CORRECTED)
                case ItemAction.SET_QUANTITY:
                    if quantity is None:
                        raise InvalidAction("quantity")
                    try:
                        change = set_quantity(batch, quantity)
                    except ValueError as error:
                        raise InvalidAction("quantity") from error
                case _:
                    raise InvalidAction("action")
            await repo.save(change.after, group_id=group_id)
            applied = AppliedChange(change.op_type, change.before, change.after)
            await uow.repo(OperationLog).add(
                OperationGroup(
                    id=group_id,
                    user_id=user_id,
                    created_at=now,
                    source=APP_SOURCE,
                    changes=(_logged(applied),),
                )
            )
        return group_id, change.after

    async def undo(self, user_id: UUID, group_id: UUID) -> UndoOutcome:
        now = self._clock.now()
        async with self._uow.for_user(user_id) as uow:
            await _locked_context(uow, user_id)
            group = await uow.repo(OperationLog).get(group_id)
            if group is None:
                return UndoOutcome.NOT_FOUND
            if group.undone_at is not None:
                return UndoOutcome.ALREADY_UNDONE
            return await self._undo_group(uow, user_id, group, now=now)

    async def undo_last(self, user_id: UUID) -> UndoOutcome:
        """Select and undo the actor's latest live group under one household lock."""
        now = self._clock.now()
        async with self._uow.for_user(user_id) as uow:
            await _locked_context(uow, user_id)
            group = await uow.repo(OperationLog).latest_for_user(user_id)
            if group is None:
                return UndoOutcome.NOT_FOUND
            return await self._undo_group(uow, user_id, group, now=now)

    async def _undo_group(
        self, uow: UnitOfWork, user_id: UUID, group: OperationGroup, *, now: datetime
    ) -> UndoOutcome:
        repo = uow.repo(BatchRepository)
        log = uow.repo(OperationLog)
        group_id = group.id
        ids = list(dict.fromkeys(c.batch_id for c in group.changes))
        last = await repo.last_groups(ids)
        if any(last.get(i) != group_id for i in ids):
            return UndoOutcome.CONFLICT
        for change in reversed(group.changes):
            if change.before is None:
                await repo.delete(change.batch_id)
            else:
                await repo.restore(from_snapshot(change.before))
        await log.mark_undone(group_id, at=now, by=user_id)
        return UndoOutcome.DONE
