"""attention.items for the kitchen (household-scoped, read through the inventory snapshot)."""

from __future__ import annotations

from shared.a2a.executor import SkillResult
from shared.a2a.request import SkillRequest
from shared.attention import AttentionAction, AttentionItem, attention_result
from shared.ports.clock import Clock
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWorkFactory

from kitchen.application.errors import NoHousehold
from kitchen.application.ports import UserLocales
from kitchen.application.service import InventoryService
from kitchen.domain.attention import MAX_EXPIRED, spoilage

OPEN = AttentionAction("agent")


class KitchenAttentionSkill:
    def __init__(
        self,
        service: InventoryService,
        uow: UnitOfWorkFactory,
        translator: Translator,
        clock: Clock,
        *,
        default_locale: str,
    ) -> None:
        self._service = service
        self._uow = uow
        self._tr = translator
        self._clock = clock
        self._default_locale = default_locale

    async def __call__(self, request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        try:
            context, active = await self._service.snapshot(request.user_id)
        except NoHousehold:
            return attention_result([])
        async with self._uow.for_user(request.user_id) as uow:
            locale = await uow.repo(UserLocales).locale(request.user_id) or self._default_locale
        # Kitchen days (ids like kitchen:today:<date>, and the expiry buckets) follow the
        # household zone; the gateway dates dismissals in the user's own zone. Members of one
        # household share a zone in practice, so the two agree.
        today = context.today(self._clock.now())
        s = spoilage(active, today)

        def t(key: str, **params: object) -> str:
            return self._tr.t(key, locale, **params)

        items = []
        for batch in sorted(s.expired, key=lambda b: (b.expires_on, str(b.pk)))[:MAX_EXPIRED]:
            past = (today - batch.expires_on).days
            items.append(
                AttentionItem(
                    f"kitchen:expired:{batch.pk}",
                    "critical",
                    -past,
                    t("attention.kitchen.expired", name=batch.display_name),
                    OPEN,
                    detail=t("attention.kitchen.expired_detail", count=past),
                )
            )
        if s.today:
            items.append(
                AttentionItem(
                    f"kitchen:today:{today.isoformat()}",
                    "high",
                    0,
                    t("attention.kitchen.today", count=len(s.today)),
                    OPEN,
                    detail=", ".join(b.display_name for b in s.today),
                )
            )
        if s.tomorrow:
            items.append(
                AttentionItem(
                    f"kitchen:tomorrow:{today.isoformat()}",
                    "normal",
                    0,
                    t("attention.kitchen.tomorrow", count=len(s.tomorrow)),
                    OPEN,
                    detail=", ".join(b.display_name for b in s.tomorrow),
                )
            )
        return attention_result(items)
