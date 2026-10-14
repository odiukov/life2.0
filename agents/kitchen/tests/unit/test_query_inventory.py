from datetime import UTC, datetime
from uuid import UUID, uuid4

from kitchen.application.ports import HouseholdContext
from kitchen.application.query_inventory import QueryInventory
from kitchen.application.service import InventoryService
from kitchen.testing import KitchenMemory, in_memory_uow, make_batch
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.config import find_locales_dir
from shared.ports.llm import LLMTask
from shared.testing.fakes import FakeLLM, FixedClock

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
A = UUID(int=1)


async def test_answers_from_inventory_in_the_users_language() -> None:
    memory = KitchenMemory(HouseholdContext(UUID(int=9), "Europe/Lisbon", {A: "Аня"}))
    batch = make_batch(id=1)
    memory.batches.rows[batch.pk] = batch
    uow = in_memory_uow(memory)
    llm = FakeLLM()
    llm.queue_text("Есть молоко до 20 октября.")
    handler = QueryInventory(
        llm=llm,
        service=InventoryService(uow, FixedClock(NOW)),
        uow=uow,
        clock=FixedClock(NOW),
        translator=JsonTranslator.from_dir(find_locales_dir()),
        default_locale="ru",
    )
    result = await handler(
        SkillRequest(
            task_id=str(uuid4()),
            context_id="c",
            text="что есть?",
            user_id=A,
            skill_id="kitchen.query",
            for_date=None,
            is_peer_call=False,
        ),
        (),
    )
    assert result.output == "Есть молоко до 20 октября."
    call = llm.calls[0]
    assert call.task is LLMTask.KITCHEN_QUERY
    assert "Russian" in call.system
    assert "молоко 3.2%" in call.system


async def test_empty_inventory_still_answers_through_the_llm() -> None:
    memory = KitchenMemory(HouseholdContext(UUID(int=9), "Europe/Lisbon", {A: "Anna"}))
    uow = in_memory_uow(memory)
    llm = FakeLLM()
    llm.queue_text("There is no food in stock.")
    handler = QueryInventory(
        llm=llm,
        service=InventoryService(uow, FixedClock(NOW)),
        uow=uow,
        clock=FixedClock(NOW),
        translator=JsonTranslator.from_dir(find_locales_dir()),
        default_locale="en",
    )
    result = await handler(
        SkillRequest(
            task_id=str(uuid4()),
            context_id="c",
            text="What is in stock?",
            user_id=A,
            skill_id="kitchen.query",
            for_date=None,
            is_peer_call=False,
        ),
        (),
    )
    assert result.output == "There is no food in stock."
    assert len(llm.calls) == 1
    assert "(empty)" in llm.calls[0].system


async def test_user_locale_and_household_local_day_reach_query_prompt() -> None:
    memory = KitchenMemory(HouseholdContext(UUID(int=9), "Europe/Moscow", {A: "Anna"}))
    memory.locales.locales[A] = "en"
    clock = FixedClock(datetime(2026, 10, 13, 23, 30, tzinfo=UTC))
    uow = in_memory_uow(memory)
    llm = FakeLLM()
    llm.queue_text("Nothing in stock.")
    handler = QueryInventory(
        llm=llm,
        service=InventoryService(uow, clock),
        uow=uow,
        clock=clock,
        translator=JsonTranslator.from_dir(find_locales_dir()),
        default_locale="ru",
    )
    result = await handler(
        SkillRequest(
            task_id=str(uuid4()),
            context_id="c",
            text="What is in stock?",
            user_id=A,
            skill_id="kitchen.query",
            for_date=None,
            is_peer_call=False,
        ),
        (),
    )
    assert result.output == "Nothing in stock."
    assert "English" in llm.calls[0].system
    assert "2026-10-14" in llm.calls[0].system


async def test_no_household_returns_localized_failure_before_llm_call() -> None:
    memory = KitchenMemory(None)
    uow = in_memory_uow(memory)
    llm = FakeLLM()
    handler = QueryInventory(
        llm=llm,
        service=InventoryService(uow, FixedClock(NOW)),
        uow=uow,
        clock=FixedClock(NOW),
        translator=JsonTranslator.from_dir(find_locales_dir()),
        default_locale="en",
    )
    result = await handler(
        SkillRequest(
            task_id=str(uuid4()),
            context_id="c",
            text="What is in stock?",
            user_id=A,
            skill_id="kitchen.query",
            for_date=None,
            is_peer_call=False,
        ),
        (),
    )
    assert result.failed
    assert result.output == "I couldn't find your household. Please reopen the app."
    assert llm.calls == []


async def test_query_provider_down_returns_localized_failure() -> None:
    from shared.ports.llm import LLMUnavailable

    memory = KitchenMemory(HouseholdContext(UUID(int=9), "Europe/Lisbon", {A: "Anna"}))
    uow = in_memory_uow(memory)
    llm = FakeLLM()
    llm.queue_text(LLMUnavailable("down"))
    handler = QueryInventory(
        llm=llm,
        service=InventoryService(uow, FixedClock(NOW)),
        uow=uow,
        clock=FixedClock(NOW),
        translator=JsonTranslator.from_dir(find_locales_dir()),
        default_locale="en",
    )
    result = await handler(
        SkillRequest(
            task_id=str(uuid4()),
            context_id="c",
            text="What is in stock?",
            user_id=A,
            skill_id="kitchen.query",
            for_date=None,
            is_peer_call=False,
        ),
        (),
    )
    assert result.failed
    assert result.output.startswith("I can't process messages")
