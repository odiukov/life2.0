from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

from kitchen.application.attention import KitchenAttentionSkill
from kitchen.application.ports import HouseholdContext
from kitchen.application.service import InventoryService
from kitchen.domain.attention import spoilage
from kitchen.testing import KitchenMemory, in_memory_uow, make_batch
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.skill_ids import Attention
from shared.testing.attention_contract import assert_attention_contract
from shared.testing.fakes import FixedClock

LOCALES = Path(__file__).resolve().parents[4] / "packages" / "i18n" / "locales"
TR = JsonTranslator.from_dir(LOCALES)
NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
TODAY = date(2026, 10, 16)
A = UUID(int=1)


def req() -> SkillRequest:
    return SkillRequest(str(uuid4()), "c", "", A, Attention.ITEMS, None, False, {})


def test_spoilage_buckets() -> None:
    b = [
        make_batch(id=1, expires_on=date(2026, 10, 14)),
        make_batch(id=2, expires_on=TODAY),
        make_batch(id=3, expires_on=date(2026, 10, 17)),
        make_batch(id=4, expires_on=date(2026, 10, 25)),
    ]
    s = spoilage(b, TODAY)
    assert [x.id for x in s.expired] == [UUID(int=1)]
    assert [x.id for x in s.today] == [UUID(int=2)]
    assert [x.id for x in s.tomorrow] == [UUID(int=3)]


async def run(*batches, locale: str = "en", context: HouseholdContext | None = None):  # type: ignore[no-untyped-def]
    memory = KitchenMemory(context or HouseholdContext(UUID(int=9), "Europe/Kyiv", {A: "Аня"}))
    for batch in batches:
        memory.batches.rows[batch.id] = batch
    memory.locales.locales[A] = locale
    uow = in_memory_uow(memory)
    skill = KitchenAttentionSkill(
        InventoryService(uow, FixedClock(NOW)), uow, TR, FixedClock(NOW), default_locale="en"
    )
    result = await skill(req(), ())
    assert_attention_contract(result.data)
    return result.data["items"]  # type: ignore[index]


async def test_expired_is_critical_per_batch_oldest_first_and_groups_are_counted() -> None:
    items = await run(
        make_batch(id=1, display_name="курица", expires_on=date(2026, 10, 15)),
        make_batch(id=2, display_name="сыр", expires_on=date(2026, 10, 12)),
        make_batch(id=3, expires_on=TODAY),
        make_batch(id=4, expires_on=TODAY),
        make_batch(id=5, expires_on=date(2026, 10, 17)),
    )
    assert [(i["level"], i["text"]) for i in items] == [
        ("critical", "Throw out сыр"),
        ("critical", "Throw out курица"),
        ("high", "2 items spoil today"),
        ("normal", "1 item spoils tomorrow"),
    ]
    assert items[0]["id"] == f"kitchen:expired:{UUID(int=2)}"
    assert items[0]["detail"] == "Expired 4 days ago"
    assert items[2]["id"] == "kitchen:today:2026-10-16"
    assert all(i["action"] == {"type": "agent"} for i in items)


async def test_at_most_five_expired_items() -> None:
    items = await run(*(make_batch(id=n, expires_on=date(2026, 10, 1)) for n in range(1, 9)))
    assert len(items) == 5


async def test_russian_plural() -> None:
    items = await run(*(make_batch(id=n, expires_on=TODAY) for n in range(1, 4)), locale="ru")
    assert items[0]["text"] == "3 продукта портятся сегодня"


async def test_no_household_is_empty() -> None:
    memory = KitchenMemory(None)
    uow = in_memory_uow(memory)
    skill = KitchenAttentionSkill(
        InventoryService(uow, FixedClock(NOW)), uow, TR, FixedClock(NOW), default_locale="en"
    )
    result = await skill(req(), ())
    assert result.data == {"items": []}
