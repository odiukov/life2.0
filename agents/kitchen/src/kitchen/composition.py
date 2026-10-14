"""Composition root: the only place that chooses adapters."""

from __future__ import annotations

from dataclasses import dataclass

from a2a.types import AgentCard
from shared.a2a.executor import SkillExecutor, SkillHandler
from shared.adapters.a2a.task_records import SqlTaskRecords
from shared.adapters.a2a.task_store import SqlTaskStore
from shared.adapters.clock import SystemClock
from shared.adapters.db.engine import create_engine
from shared.adapters.i18n import JsonTranslator
from shared.adapters.llm.build import build_llm_provider
from shared.observability.logging import configure_logging
from shared.ports.clock import Clock
from shared.ports.llm import LLMProvider
from shared.skill_ids import Kitchen
from sqlalchemy.ext.asyncio import AsyncEngine

from kitchen.adapters.a2a.card import build_agent_card
from kitchen.adapters.db import kitchen_uow
from kitchen.adapters.matching import RapidfuzzMatcher
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


def build_runtime(
    settings: KitchenSettings,
    *,
    llm: LLMProvider | None = None,
    clock: Clock | None = None,
    matcher: TextMatcher | None = None,
) -> KitchenRuntime:
    configure_logging(settings.telemetry)
    engine = create_engine(settings.database)
    uow = kitchen_uow(engine)
    llm = llm if llm is not None else build_llm_provider(settings)
    clock = clock if clock is not None else SystemClock()
    matcher = matcher if matcher is not None else RapidfuzzMatcher()
    translator = JsonTranslator.from_dir(settings.i18n_locales_dir)
    service = InventoryService(uow, clock)
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
    )
