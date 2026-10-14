"""Send one daily kitchen digest after a household's local digest time."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared.observability.logging import get_logger
from shared.ports.clock import Clock
from shared.ports.notifications import Notification, NotificationSender
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWork, UnitOfWorkFactory

from kitchen.application.ports import (
    BatchRepository,
    DigestRuns,
    DueDigest,
    DueDigests,
    HouseholdContext,
    HouseholdView,
    UserLocales,
)
from kitchen.domain.digest import DigestView, build_digest
from kitchen.domain.model import Batch

SHOWN = 3
logger = get_logger(__name__)


class SendDueDigests:
    def __init__(
        self,
        uow: UnitOfWorkFactory,
        sender: NotificationSender,
        translator: Translator,
        clock: Clock,
        *,
        default_locale: str,
    ) -> None:
        self._uow = uow
        self._sender = sender
        self._t = translator
        self._clock = clock
        self._default_locale = default_locale

    async def __call__(self) -> int:
        now = self._clock.now()
        async with self._uow.system() as uow:
            due = await uow.repo(DueDigests).due(now)
        notified = 0
        for item in due:
            try:
                notified += await self._one(item)
            except Exception as exc:
                logger.warning("kitchen_digest_failed", error_type=type(exc).__name__)
        return notified

    async def _valid(self, uow: UnitOfWork, item: DueDigest) -> bool:
        context = await uow.repo(HouseholdView).current()
        if context is None or context.household_id != item.household_id:
            return False
        await uow.repo(BatchRepository).lock()
        current = await uow.repo(HouseholdView).current()
        return current is not None and self._matches(current, item, self._clock.now())

    @staticmethod
    def _matches(context: HouseholdContext, item: DueDigest, now: datetime) -> bool:
        local = now.astimezone(context.zone())
        return (
            context.household_id == item.household_id
            and context.timezone == item.timezone
            and context.today(now) == item.local_date
            and local.time().replace(tzinfo=None) >= context.digest_time
            and (context.owner_id is None or context.owner_id == item.owner_id)
            and item.owner_id in context.members
            and len(context.members) == len(item.member_ids)
            and set(context.members) == set(item.member_ids)
        )

    async def _one(self, item: DueDigest) -> int:
        # The discovery row is a snapshot. Membership mutations share this lock;
        # revalidate before reading inventory and claiming the daily run.
        async with self._uow.for_user(item.owner_id) as uow:
            if not await self._valid(uow, item):
                return 0
            runs = uow.repo(DigestRuns)
            bind = getattr(runs, "bind", None)
            if callable(bind):
                bind(item.household_id)
            if not await runs.claim(item.local_date):
                return 0
            view = build_digest(await uow.repo(BatchRepository).list_active(), item.local_date)
        # Claim is committed before delivery. An inbox failure may lose today's
        # digest; repeating a notification would violate the at-most-once contract.
        if view.is_empty:
            return 0
        locales: dict[UUID, str] = {}
        for member in item.member_ids:
            async with self._uow.for_user(member) as uow:
                locales[member] = await uow.repo(UserLocales).locale(member) or self._default_locale
        # Membership could have changed after the claim. Keep the same household
        # lock through delivery, so former members never get old-household data.
        async with self._uow.for_user(item.owner_id) as uow:
            if not await self._valid(uow, item):
                return 0
            for member in item.member_ids:
                await self._sender.send([member], self._render(view, item, locales[member]))
        return 1

    def _when(self, batch: Batch, item: DueDigest) -> str:
        days = (batch.expires_on - item.local_date).days
        return (
            "expired"
            if days < 0
            else "today"
            if days == 0
            else "tomorrow"
            if days == 1
            else "check"
        )

    def _render(self, view: DigestView, item: DueDigest, locale: str) -> Notification:
        items = view.items()
        parts = [
            self._t.t(
                "kitchen.digest.item",
                locale,
                name=batch.display_name,
                when=self._t.t(f"kitchen.digest.when.{self._when(batch, item)}", locale),
            )
            for batch in items[:SHOWN]
        ]
        remaining = len(items) - SHOWN + view.hidden
        if remaining > 0:
            parts.append(self._t.t("kitchen.digest.more", locale, count=remaining))
        return Notification(
            kind="kitchen.digest",
            title=self._t.t("kitchen.digest.title", locale),
            body=", ".join(parts),
            data={"route": "/kitchen"},
        )
