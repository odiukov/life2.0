"""Composition root: the only place that chooses adapters."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from a2a.types import AgentCard
from shared.a2a.executor import SkillExecutor, SkillHandler
from shared.adapters.a2a.task_records import SqlTaskRecords
from shared.adapters.a2a.task_store import SqlTaskStore
from shared.adapters.clock import SystemClock
from shared.adapters.db.engine import create_engine
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.adapters.i18n import JsonTranslator
from shared.adapters.llm.build import build_llm_provider
from shared.adapters.notifications import build_notification_sender, notification_repositories
from shared.adapters.scheduler import ApschedulerScheduler
from shared.observability.logging import configure_logging
from shared.ports.clock import Clock
from shared.ports.llm import LLMProvider
from shared.ports.notifications import NotificationSender
from shared.ports.scheduler import Scheduler
from shared.skill_ids import Attention, Kitchen
from sqlalchemy.ext.asyncio import AsyncEngine

from kitchen.adapters.a2a.card import build_agent_card
from kitchen.adapters.db import digest_repositories, kitchen_uow
from kitchen.adapters.matching import RapidfuzzMatcher
from kitchen.application.attention import KitchenAttentionSkill
from kitchen.application.digest_job import SendDueDigests
from kitchen.application.ports import TextMatcher
from kitchen.application.query_inventory import QueryInventory
from kitchen.application.service import InventoryService
from kitchen.application.structured import DigestSkill, InventorySkill, ItemActionSkill, UndoSkill
from kitchen.application.update_inventory import UpdateInventory
from kitchen.settings import KitchenSettings

AGENT = "kitchen"


@dataclass(frozen=True, slots=True)
class KitchenRuntime:
    executor: SkillExecutor
    task_store: SqlTaskStore
    card: AgentCard
    engine: AsyncEngine
    service: InventoryService
    scheduler: Scheduler
    digest_job: SendDueDigests
    http: httpx.AsyncClient


def build_runtime(
    settings: KitchenSettings,
    *,
    llm: LLMProvider | None = None,
    clock: Clock | None = None,
    matcher: TextMatcher | None = None,
    scheduler: Scheduler | None = None,
    sender: NotificationSender | None = None,
    http: httpx.AsyncClient | None = None,
) -> KitchenRuntime:
    configure_logging(settings.telemetry)
    engine = create_engine(settings.database)
    uow = kitchen_uow(engine, extra=digest_repositories())
    llm = llm if llm is not None else build_llm_provider(settings)
    clock = clock if clock is not None else SystemClock()
    matcher = matcher if matcher is not None else RapidfuzzMatcher()
    translator = JsonTranslator.from_dir(settings.i18n_locales_dir)
    service = InventoryService(uow, clock)
    http = http or httpx.AsyncClient()
    sender = sender or build_notification_sender(
        settings.notifications,
        uow=SqlUnitOfWorkFactory(engine, notification_repositories()),
        http=http,
        clock=clock,
    )
    digest_job = SendDueDigests(
        uow, sender, translator, clock, default_locale=settings.default_locale
    )
    scheduler = scheduler or ApschedulerScheduler()

    async def run_digest() -> None:
        await digest_job()

    scheduler.add_interval("kitchen-digest", run_digest, minutes=settings.digest_interval_minutes)
    handlers: dict[str, SkillHandler] = {
        Kitchen.UPDATE_INVENTORY: UpdateInventory(
            llm=llm,
            service=service,
            uow=uow,
            clock=clock,
            translator=translator,
            matcher=matcher,
            default_locale=settings.default_locale,
        ),
        Kitchen.QUERY: QueryInventory(
            llm=llm,
            service=service,
            uow=uow,
            clock=clock,
            translator=translator,
            default_locale=settings.default_locale,
        ),
        Kitchen.INVENTORY: InventorySkill(service),
        Kitchen.DIGEST: DigestSkill(service, clock),
        Kitchen.ITEM_ACTION: ItemActionSkill(service),
        Kitchen.UNDO: UndoSkill(service),
        Attention.ITEMS: KitchenAttentionSkill(
            service, uow, translator, clock, default_locale=settings.default_locale
        ),
    }
    executor = SkillExecutor(
        agent=AGENT,
        handlers=handlers,
        peers=[],
        llm=llm,
        task_records=SqlTaskRecords(engine),
        clock=clock,
        routable=[Kitchen.UPDATE_INVENTORY, Kitchen.QUERY],
    )
    return KitchenRuntime(
        executor=executor,
        task_store=SqlTaskStore(engine, agent=AGENT),
        card=build_agent_card(settings.kitchen_agent_url),
        engine=engine,
        service=service,
        scheduler=scheduler,
        digest_job=digest_job,
        http=http,
    )
