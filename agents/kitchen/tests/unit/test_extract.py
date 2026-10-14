from datetime import date

import pytest
from kitchen.application.extract import ExtractionContext, extract_operations
from kitchen.application.schema import OperationList
from shared.ports.llm import LLMInvalidOutput, LLMTask, LLMUnavailable
from shared.testing.fakes import FakeLLM

CTX = ExtractionContext(
    text="купил молоко", today=date(2026, 10, 13), timezone="Europe/Lisbon", inventory=""
)


async def test_prompt_carries_today_inventory_and_clarification() -> None:
    llm = FakeLLM()
    llm.queue_structured(OperationList())
    ctx = ExtractionContext(
        text="российский",
        today=date(2026, 10, 13),
        timezone="Europe/Lisbon",
        inventory="- сыр | сыр | 1 pcs | fridge | opened=no | expires 2026-10-20",
        clarification='You asked about "сыр"',
    )
    await extract_operations(llm, ctx)
    call = llm.calls[0]
    assert call.task is LLMTask.KITCHEN_EXTRACT
    assert "2026-10-13 (Tuesday)" in call.system
    assert "- сыр | сыр" in call.system
    assert 'You asked about "сыр"' in call.system
    assert call.user == "российский"


async def test_one_repair_attempt_then_none() -> None:
    llm = FakeLLM()
    llm.queue_structured(LLMInvalidOutput("{}", "bad"), LLMInvalidOutput("{}", "still bad"))
    assert await extract_operations(llm, CTX) is None
    assert "rejected by the validator" in llm.calls[1].user


async def test_unavailable_provider_propagates() -> None:
    llm = FakeLLM()
    llm.queue_structured(LLMUnavailable("down"))
    with pytest.raises(LLMUnavailable):
        await extract_operations(llm, CTX)
