from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from kitchen.adapters.matching import RapidfuzzMatcher
from kitchen.application.ports import HouseholdContext
from kitchen.application.schema import OperationList
from kitchen.application.service import InventoryService
from kitchen.application.update_inventory import UpdateInventory
from kitchen.testing import KitchenMemory, in_memory_uow
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.config import find_locales_dir
from shared.ports.llm import LLMUnavailable
from shared.testing.fakes import FakeLLM, FixedClock, LLMCall

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
A = UUID(int=1)
ADD_MILK = {
    "adds": [
        {
            "name": "молоко",
            "display_name": "молоко",
            "quantity": 1,
            "unit": "l",
            "location": "fridge",
            "category": "dairy",
            "shelf_life_days": 7,
        }
    ]
}


def setup(
    responder: Callable[[LLMCall], object] | None = None,
) -> tuple[UpdateInventory, FakeLLM, KitchenMemory, FixedClock]:
    memory = KitchenMemory(HouseholdContext(UUID(int=9), "Europe/Lisbon", {A: "Аня"}))
    clock = FixedClock(NOW)
    uow = in_memory_uow(memory)
    llm = FakeLLM(responder=responder)
    handler = UpdateInventory(
        llm=llm,
        service=InventoryService(uow, clock),
        uow=uow,
        clock=clock,
        translator=JsonTranslator.from_dir(find_locales_dir()),
        matcher=RapidfuzzMatcher(),
        default_locale="ru",
    )
    return handler, llm, memory, clock


def req(text: str) -> SkillRequest:
    return SkillRequest(
        task_id=str(uuid4()),
        context_id="c",
        text=text,
        user_id=A,
        skill_id="kitchen.update_inventory",
        for_date=None,
        is_peer_call=False,
    )


async def test_add_replies_with_lines_undo_hint_and_group_data() -> None:
    handler, llm, memory, _ = setup()
    llm.queue_structured(ADD_MILK)
    result = await handler(req("купил литр молока"), ())
    assert result.output.startswith("Записал:\n• молоко — 1 л (до ")
    assert result.output.endswith("Скажи «отмени», если что-то не так.")
    assert result.data is not None
    assert UUID(str(result.data["group_id"])) in memory.log.groups


async def test_ambiguous_reference_asks_and_the_answer_completes_it() -> None:
    handler, llm, memory, _ = setup()
    llm.queue_structured(
        {
            "adds": [
                {
                    "name": "сыр российский",
                    "display_name": "сыр",
                    "quantity": 1,
                    "unit": "pcs",
                    "location": "fridge",
                    "category": "dairy",
                    "shelf_life_days": 14,
                },
                {
                    "name": "сыр моцарелла",
                    "display_name": "сыр",
                    "quantity": 1,
                    "unit": "pcs",
                    "location": "fridge",
                    "category": "dairy",
                    "shelf_life_days": 7,
                },
            ]
        }
    )
    await handler(req("купил два сыра"), ())
    llm.queue_structured({"consumes": [{"item_ref": "сыр"}]})
    asked = await handler(req("доели сыр"), ())
    assert asked.output.startswith("Что именно — «сыр»?")
    assert "сыр моцарелла" in asked.output
    assert "сыр российский" in asked.output
    assert asked.data is None
    assert A in memory.clarifications.rows
    llm.queue_structured({"consumes": [{"item_ref": "сыр моцарелла"}]})
    done = await handler(req("моцареллу"), ())
    assert "доели сыр" in llm.calls[-1].system  # the original message is in the clarification block
    assert done.output.startswith("Списал:")
    assert A not in memory.clarifications.rows


async def test_unknown_reference_is_reported_and_the_rest_applies() -> None:
    handler, llm, _, _ = setup()
    llm.queue_structured({**ADD_MILK, "discards": [{"item_ref": "кефир"}]})
    result = await handler(req("купил молоко, выкинул кефир"), ())
    assert "Записал:" in result.output
    assert "Не нашёл в запасах: кефир" in result.output


async def test_undo_last_from_chat() -> None:
    handler, llm, memory, _ = setup()
    llm.queue_structured(ADD_MILK)
    await handler(req("купил молоко"), ())
    llm.queue_structured(OperationList(undo_last=True))
    undone = await handler(req("отмени"), ())
    assert undone.output == "Отменил."
    assert memory.batches.rows == {}
    llm.queue_structured(OperationList(undo_last=True))
    assert (await handler(req("отмени"), ())).output == "Нечего отменять."


async def test_unrelated_message_is_not_understood_and_keeps_nothing() -> None:
    handler, llm, memory, _ = setup()
    llm.queue_structured(OperationList())
    result = await handler(req("привет"), ())
    assert result.output.startswith("Не понял")
    assert not result.failed
    assert memory.batches.rows == {}


async def test_provider_down_is_a_failed_task_with_a_localized_message() -> None:
    handler, llm, _, _ = setup()
    llm.queue_structured(LLMUnavailable("down"))
    result = await handler(req("купил молоко"), ())
    assert result.failed
    assert result.output.startswith("Сейчас не могу")


async def test_expired_clarification_is_ignored() -> None:
    handler, llm, _memory, clock = setup()
    llm.queue_structured(
        {
            "adds": [
                {
                    "name": "сыр российский",
                    "display_name": "сыр",
                    "quantity": 1,
                    "unit": "pcs",
                    "location": "fridge",
                    "category": "dairy",
                    "shelf_life_days": 14,
                },
                {
                    "name": "сыр моцарелла",
                    "display_name": "сыр",
                    "quantity": 1,
                    "unit": "pcs",
                    "location": "fridge",
                    "category": "dairy",
                    "shelf_life_days": 7,
                },
            ]
        }
    )
    await handler(req("купил два сыра"), ())
    llm.queue_structured({"consumes": [{"item_ref": "сыр"}]})
    await handler(req("доели сыр"), ())
    clock.advance(minutes=31)
    llm.queue_structured(ADD_MILK)
    await handler(req("купил молоко"), ())
    assert "(none)" in llm.calls[-1].system


async def test_units_question_rolls_back_addition_then_answer_applies_original_message() -> None:
    handler, llm, memory, _ = setup()
    llm.queue_structured(ADD_MILK)
    await handler(req("купил молоко"), ())
    llm.queue_structured(
        {
            "adds": [
                {
                    "name": "bread",
                    "display_name": "bread",
                    "quantity": 1,
                    "unit": "pcs",
                    "location": "pantry",
                    "category": "bakery",
                    "shelf_life_days": 4,
                }
            ],
            "consumes": [{"item_ref": "молоко", "quantity": 1, "unit": "pcs"}],
        }
    )
    result = await handler(req("купил хлеб, выпил одну штуку молока"), ())
    assert result.output.startswith("Для «молоко» другие единицы (мл)")
    assert len(memory.batches.rows) == 1
    assert len(memory.log.groups) == 1
    llm.queue_structured(
        {
            "adds": [
                {
                    "name": "bread",
                    "display_name": "bread",
                    "quantity": 1,
                    "unit": "pcs",
                    "location": "pantry",
                    "category": "bakery",
                    "shelf_life_days": 4,
                }
            ],
            "consumes": [{"item_ref": "молоко", "quantity": 0.5, "unit": "l"}],
        }
    )
    done = await handler(req("пол-литра"), ())
    assert "Записал:" in done.output
    assert "Списал:" in done.output
    assert len(memory.batches.rows) == 2
    assert A not in memory.clarifications.rows


async def test_mixed_query_reads_inventory_after_changes_commit() -> None:
    handler, llm, memory, _ = setup()
    llm.queue_structured({**ADD_MILK, "queries": [{"question": "что есть?"}]})
    llm.queue_text("Есть литр молока.")
    result = await handler(req("купил молоко, что есть?"), ())
    assert "Записал:" in result.output
    assert "Есть литр молока." in result.output
    assert "молоко | молоко | 1000 ml" in llm.calls[-1].system
    assert len(memory.log.groups) == 1


async def test_all_missing_refs_report_once_without_group_data() -> None:
    handler, llm, memory, _ = setup()
    llm.queue_structured(
        {
            "updates": [{"item_ref": "кефир", "opened": True}],
            "discards": [{"item_ref": "кефир"}],
            "consumes": [{"item_ref": "кефир"}],
        }
    )
    result = await handler(req("кефир открыт и закончился"), ())
    assert result.output == "Не нашёл в запасах: кефир"
    assert result.data is None
    assert memory.log.groups == {}


async def test_no_household_returns_localized_failure_before_extraction() -> None:
    handler, llm, memory, _ = setup()
    memory.context = None
    result = await handler(req("купил молоко"), ())
    assert result.failed
    assert result.output == "Не нашёл твой дом. Открой приложение ещё раз."
    assert llm.calls == []


async def test_preferred_locale_is_used_and_undo_clears_pending_question() -> None:
    from kitchen.application.ports import PendingClarification

    handler, llm, memory, _ = setup()
    memory.locales.locales[A] = "en"
    llm.queue_structured(ADD_MILK)
    result = await handler(req("bought milk"), ())
    assert result.output.startswith("Added:")
    memory.clarifications.rows[A] = PendingClarification(
        text="used cheese",
        ref="cheese",
        reason="ambiguous",
        candidates=("cheddar", "brie"),
        expires_at=NOW + timedelta(minutes=30),
    )
    llm.queue_structured(OperationList(undo_last=True))
    result = await handler(req("undo"), ())
    assert result.output == "Undone."
    assert A not in memory.clarifications.rows


async def test_expired_pending_is_deleted_even_when_new_message_is_unrelated() -> None:
    from kitchen.application.ports import PendingClarification

    handler, llm, memory, _ = setup()
    memory.clarifications.rows[A] = PendingClarification(
        text="used cheese",
        ref="cheese",
        reason="ambiguous",
        candidates=("cheddar", "brie"),
        expires_at=NOW,
    )
    llm.queue_structured(OperationList())
    await handler(req("hello"), ())
    assert A not in memory.clarifications.rows
    assert "(none)" in llm.calls[0].system


async def test_membership_lost_during_extraction_returns_localized_failure() -> None:
    def leave(_call: LLMCall) -> object:
        memory.context = None
        return ADD_MILK

    handler, _llm, memory, _ = setup(responder=leave)
    result = await handler(req("bought milk"), ())
    assert result.failed
    assert result.output == "Не нашёл твой дом. Открой приложение ещё раз."
    assert not memory.batches.rows


async def test_snapshot_reference_gone_before_apply_is_reported_without_hint() -> None:
    from dataclasses import replace

    from kitchen.domain.model import Status

    def finish(_call: LLMCall) -> object:
        for pk, batch in memory.batches.rows.items():
            memory.batches.rows[pk] = replace(batch, status=Status.CONSUMED)
        return {"consumes": [{"item_ref": "молоко"}]}

    handler, llm, memory, _ = setup(responder=finish)
    llm.queue_structured(ADD_MILK)
    await handler(req("купил молоко"), ())
    result = await handler(req("доели молоко"), ())
    assert result.output == "Не нашёл в запасах: молоко"
    assert result.data is None
    assert len(memory.log.groups) == 1


@pytest.mark.parametrize("expires_after_minutes", [30, 0])
async def test_unrelated_ambiguity_replaces_previous_command_and_next_prompt(
    expires_after_minutes: int,
) -> None:
    from kitchen.application.ports import PendingClarification
    from kitchen.testing import make_batch

    handler, llm, memory, _ = setup()
    for index, name in enumerate(("milk whole", "milk skimmed"), start=1):
        batch = make_batch(id=index, name=name, display_name=name)
        memory.batches.rows[batch.pk] = batch
    memory.clarifications.rows[A] = PendingClarification(
        text="used cheese",
        ref="cheese",
        reason="ambiguous",
        candidates=("cheese cheddar", "cheese brie"),
        expires_at=NOW + timedelta(minutes=expires_after_minutes),
    )
    llm.queue_structured({"consumes": [{"item_ref": "milk"}]})
    asked = await handler(req("finished milk"), ())
    assert asked.output.startswith("Что именно — «milk»?")
    assert memory.clarifications.rows[A].text == "finished milk"
    assert memory.clarifications.rows[A].ref == "milk"
    assert memory.clarifications.rows[A].expires_at == NOW + timedelta(minutes=30)

    llm.queue_structured({"consumes": [{"item_ref": "milk whole"}]})
    done = await handler(req("whole"), ())
    assert "used cheese" not in llm.calls[-1].system
    assert "finished milk" in llm.calls[-1].system
    assert done.output.startswith("Списал:")
    assert A not in memory.clarifications.rows


async def test_genuine_candidate_answer_preserves_original_until_units_are_clarified() -> None:
    from kitchen.application.ports import PendingClarification
    from kitchen.domain.model import Unit
    from kitchen.testing import make_batch

    handler, llm, memory, _ = setup()
    for index, name in enumerate(("cheese cheddar", "cheese brie"), start=1):
        batch = make_batch(id=index, name=name, display_name=name, unit=Unit.G)
        memory.batches.rows[batch.pk] = batch
    original = "used cheese and bought bread"
    memory.clarifications.rows[A] = PendingClarification(
        text=original,
        ref="cheese",
        reason="ambiguous",
        candidates=("cheese cheddar", "cheese brie"),
        expires_at=NOW + timedelta(minutes=30),
    )
    bread = {
        "name": "bread",
        "display_name": "bread",
        "quantity": 1,
        "unit": "pcs",
        "location": "pantry",
        "category": "bakery",
        "shelf_life_days": 4,
    }
    llm.queue_structured(
        {
            "adds": [bread],
            "consumes": [{"item_ref": "cheese brie", "quantity": 1, "unit": "pcs"}],
        }
    )
    asked = await handler(req("brie, one piece"), ())
    assert asked.output.startswith("Для «cheese brie» другие единицы")
    assert memory.clarifications.rows[A].text == original + "\nbrie, one piece"
    assert memory.clarifications.rows[A].reason == "incompatible_units"
    assert len(memory.batches.rows) == 2

    llm.queue_structured(
        {
            "adds": [bread],
            "consumes": [{"item_ref": "cheese brie", "quantity": 200, "unit": "g"}],
        }
    )
    done = await handler(req("200 grams"), ())
    assert original in llm.calls[-1].system
    assert "brie, one piece" in llm.calls[-1].system
    assert "Записал:" in done.output
    assert "Списал:" in done.output
    assert len(memory.batches.rows) == 3
    assert A not in memory.clarifications.rows


async def test_quantity_answer_for_addition_preserves_original_pending_message() -> None:
    from kitchen.application.ports import PendingClarification

    handler, llm, memory, _ = setup()
    memory.clarifications.rows[A] = PendingClarification(
        text="bought milk and bread",
        ref="bread",
        reason="invalid_quantity",
        candidates=(),
        expires_at=NOW + timedelta(minutes=30),
    )
    llm.queue_structured(
        {
            **ADD_MILK,
            "adds": [
                *ADD_MILK["adds"],
                {
                    "name": "bread",
                    "display_name": "bread",
                    "quantity": 0.0001,
                    "unit": "pcs",
                    "location": "pantry",
                    "category": "bakery",
                    "shelf_life_days": 4,
                },
            ],
        }
    )
    await handler(req("a crumb"), ())
    assert memory.clarifications.rows[A].text == "bought milk and bread\na crumb"
    assert not memory.batches.rows
