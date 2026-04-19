import pytest

from agents.medication.app.registry import (
    create, list_active, find_by_name, archive, normalize_name,
)


def test_normalize_name_kebabs():
    assert normalize_name("Vitamin D") == "vitamin-d"
    assert normalize_name("  IRON ") == "iron"
    assert normalize_name("") == ""
    assert normalize_name("омега-3 рыбий жир") == "омега-3-рыбий-жир"  # keeps unicode


@pytest.mark.asyncio
async def test_create_then_find_then_archive():
    mid = await create(
        name="Magnesium",
        dose="200mg",
        schedule="daily 21:00",
        notes=None,
    )
    got = await find_by_name("magnesium")
    assert got is not None and got["id"] == mid
    actives = await list_active()
    assert any(a["id"] == mid for a in actives)
    assert await archive(mid) is True
    assert (await find_by_name("magnesium")) is None
