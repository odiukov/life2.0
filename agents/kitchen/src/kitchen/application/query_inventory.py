"""kitchen.query: answer a question about the stock."""

from __future__ import annotations

from shared.a2a.executor import SkillResult
from shared.a2a.request import SkillRequest
from shared.ports.clock import Clock
from shared.ports.llm import LLMError, LLMProvider
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWorkFactory

from kitchen.application.errors import NoHousehold
from kitchen.application.inventory_text import format_inventory
from kitchen.application.ports import UserLocales
from kitchen.application.query import answer_query
from kitchen.application.rendering import KitchenText
from kitchen.application.service import InventoryService


class QueryInventory:
    def __init__(
        self,
        *,
        llm: LLMProvider,
        service: InventoryService,
        uow: UnitOfWorkFactory,
        clock: Clock,
        translator: Translator,
        default_locale: str,
    ) -> None:
        self._llm = llm
        self._service = service
        self._uow = uow
        self._clock = clock
        self._text = KitchenText(translator)
        self._default_locale = default_locale

    async def __call__(self, request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        async with self._uow.for_user(request.user_id) as uow:
            locale = await uow.repo(UserLocales).locale(request.user_id) or self._default_locale
        try:
            context, active = await self._service.snapshot(request.user_id)
        except NoHousehold:
            return SkillResult(
                output=self._text.text("kitchen.errors.no_household", locale), failed=True
            )
        try:
            answer = await answer_query(
                self._llm,
                question=request.text,
                inventory=format_inventory(active),
                today=context.today(self._clock.now()),
                locale=locale,
            )
        except LLMError:
            return SkillResult(
                output=self._text.text("kitchen.errors.llm_unavailable", locale), failed=True
            )
        return SkillResult(output=answer)
