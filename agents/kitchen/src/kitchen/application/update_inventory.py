"""kitchen.update_inventory: free text in, applied changes or one clarifying question out."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from uuid import UUID

from shared.a2a.executor import SkillResult
from shared.a2a.request import SkillRequest
from shared.ports.clock import Clock
from shared.ports.llm import LLMError, LLMProvider
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWorkFactory

from kitchen.application.errors import NoHousehold
from kitchen.application.extract import ExtractionContext, extract_operations
from kitchen.application.inventory_text import format_inventory
from kitchen.application.ports import (
    ClarificationRepository,
    PendingClarification,
    TextMatcher,
    UserLocales,
)
from kitchen.application.query import answer_query
from kitchen.application.rendering import KitchenText
from kitchen.application.resolve import (
    Ambiguous,
    NotFound,
    Resolved,
    build_resolution_context,
    resolve_ref,
)
from kitchen.application.schema import OperationList
from kitchen.application.service import ApplyNeedsClarification, InventoryService, _locked_context
from kitchen.domain.model import Source
from kitchen.domain.rules import normalize_name

PENDING_TTL = timedelta(minutes=30)


def _describe(pending: PendingClarification | None) -> str | None:
    if pending is None:
        return None
    options = ", ".join(pending.candidates) or "none"
    return (
        f'You asked about "{pending.ref}" (reason: {pending.reason}; options: {options}). '
        f'Their original message was: "{pending.text}"'
    )


def _clarification_original(
    text: str, pending: PendingClarification | None, ops: OperationList
) -> str:
    """Retain prior operations only when extraction refers to the pending product."""
    if pending is None:
        return text
    expected = {normalize_name(pending.ref)}
    if pending.reason == "ambiguous":
        expected.update(normalize_name(name) for name in pending.candidates)
    products = {normalize_name(ref) for ref in ops.item_refs()}
    products.update(normalize_name(item.name) for item in ops.adds)
    if products & expected:
        return f"{pending.text}\n{text}"
    return text


def _without(ops: OperationList, refs: set[str]) -> OperationList:
    return ops.model_copy(
        update={
            "consumes": [c for c in ops.consumes if c.item_ref not in refs],
            "discards": [d for d in ops.discards if d.item_ref not in refs],
            "updates": [u for u in ops.updates if u.item_ref not in refs],
        }
    )


class UpdateInventory:
    def __init__(
        self,
        *,
        llm: LLMProvider,
        service: InventoryService,
        uow: UnitOfWorkFactory,
        clock: Clock,
        translator: Translator,
        matcher: TextMatcher,
        default_locale: str,
    ) -> None:
        self._llm = llm
        self._service = service
        self._uow = uow
        self._clock = clock
        self._text = KitchenText(translator)
        self._matcher = matcher
        self._default_locale = default_locale

    async def __call__(self, request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        user = request.user_id
        now = self._clock.now()
        async with self._uow.for_user(user) as uow:
            locale = await uow.repo(UserLocales).locale(user) or self._default_locale
        try:
            return await self._execute(request, locale, now)
        except NoHousehold:
            return SkillResult(
                output=self._text.text("kitchen.errors.no_household", locale), failed=True
            )

    async def _execute(self, request: SkillRequest, locale: str, now: datetime) -> SkillResult:
        user = request.user_id
        context, active = await self._service.snapshot(user)
        async with self._uow.for_user(user) as uow:
            await _locked_context(uow, user)
            clarifications = uow.repo(ClarificationRepository)
            pending = await clarifications.get(user, now=now)
            if pending is None:
                await clarifications.delete(user)
        try:
            ops = await extract_operations(
                self._llm,
                ExtractionContext(
                    text=request.text,
                    today=context.today(now),
                    timezone=context.timezone,
                    inventory=format_inventory(active),
                    clarification=_describe(pending),
                ),
            )
        except LLMError:
            return SkillResult(
                output=self._text.text("kitchen.errors.llm_unavailable", locale), failed=True
            )
        if ops is None or ops.is_empty():
            return SkillResult(output=self._text.text("kitchen.not_understood", locale))
        if ops.undo_last:
            undo_outcome = await self._service.undo_last(user)
            await self._forget(user)
            return SkillResult(output=self._text.undo(locale, undo_outcome))

        original = _clarification_original(request.text, pending, ops)
        resolution = build_resolution_context(active, ops.adds)
        refs: dict[str, str] = {}
        missing: list[str] = []
        for ref in ops.item_refs():
            outcome = resolve_ref(ref, resolution.names, self._matcher)
            if isinstance(outcome, Resolved):
                refs[ref] = outcome.name
            elif isinstance(outcome, Ambiguous):
                return await self._ask(
                    user, locale, original, ref, "ambiguous", outcome.candidates, now
                )
            elif isinstance(outcome, NotFound):
                missing.append(ref)
        ops = _without(ops, set(missing))

        result = None
        if ops.adds or ops.updates or ops.consumes or ops.discards:
            try:
                result = await self._service.apply(user, ops=ops, refs=refs, source=Source.TEXT)
            except ApplyNeedsClarification as need:
                return await self._ask(
                    user, locale, original, need.ref, need.reason, need.candidates, now
                )
        if result is not None:
            missing = list(dict.fromkeys([*missing, *result.not_found]))
        answers: list[str] = []
        for query in ops.queries:
            current_context, current = await self._service.snapshot(user)
            try:
                answers.append(
                    await answer_query(
                        self._llm,
                        question=query.question,
                        inventory=format_inventory(current),
                        today=current_context.today(self._clock.now()),
                        locale=locale,
                    )
                )
            except LLMError:
                answers.append(self._text.text("kitchen.errors.llm_unavailable", locale))
        await self._forget(user)
        data = None
        if result is not None and result.changes:
            data = {
                "group_id": str(result.group_id),
                "changes": [{"op": c.op_type, "item_id": str(c.after.pk)} for c in result.changes],
            }
        return SkillResult(output=self._text.applied(locale, result, missing, answers), data=data)

    async def _ask(
        self,
        user: UUID,
        locale: str,
        original: str,
        ref: str,
        reason: str,
        candidates: Sequence[str],
        now: datetime,
    ) -> SkillResult:
        pending = PendingClarification(
            text=original,
            ref=ref,
            reason=reason,
            candidates=tuple(candidates),
            expires_at=now + PENDING_TTL,
        )
        async with self._uow.for_user(user) as uow:
            await _locked_context(uow, user)
            await uow.repo(ClarificationRepository).put(user, pending)
        return SkillResult(output=self._text.clarify(locale, ref, reason, pending.candidates))

    async def _forget(self, user: UUID) -> None:
        async with self._uow.for_user(user) as uow:
            await _locked_context(uow, user)
            await uow.repo(ClarificationRepository).delete(user)
