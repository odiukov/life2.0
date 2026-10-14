import json

import pytest
from kitchen.application.schema import (
    AddItem,
    ConsumeItem,
    DiscardItem,
    OperationList,
    QueryInventory,
    UpdateItem,
)
from pydantic import ValidationError


def add(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "молоко",
        "display_name": "молоко",
        "quantity": 1,
        "unit": "l",
        "location": "fridge",
        "category": "dairy",
        "shelf_life_days": 7,
    }
    base.update(overrides)
    return base


def test_add_requires_expiry_or_shelf_life() -> None:
    with pytest.raises(ValidationError, match="expires_on or shelf_life_days"):
        AddItem.model_validate(add(shelf_life_days=None))
    assert AddItem.model_validate(add(shelf_life_days=None, expires_on="2026-10-16")).expires_on
    assert AddItem.model_validate(add(shelf_life_days=0)).shelf_life_days == 0


@pytest.mark.parametrize("quantity", [0, -1, float("inf"), float("nan")])
def test_quantities_must_be_finite_and_positive(quantity: float) -> None:
    with pytest.raises(ValidationError):
        AddItem.model_validate(add(quantity=quantity))
    with pytest.raises(ValidationError):
        ConsumeItem.model_validate({"item_ref": "сыр", "quantity": quantity})


@pytest.mark.parametrize("days", [-1, 3651])
def test_shelf_life_is_bounded(days: int) -> None:
    with pytest.raises(ValidationError):
        AddItem.model_validate(add(shelf_life_days=days))
    with pytest.raises(ValidationError):
        UpdateItem(item_ref="молоко", opened_shelf_life_days=days)


def test_item_refs_order_and_dedupe() -> None:
    ops = OperationList(
        consumes=[ConsumeItem(item_ref="сыр"), ConsumeItem(item_ref="хлеб")],
        discards=[DiscardItem(item_ref="сыр")],
        updates=[UpdateItem(item_ref="молоко", opened=True)],
    )
    assert ops.item_refs() == ["молоко", "сыр", "хлеб"]
    assert not ops.is_empty()
    assert not OperationList(queries=[QueryInventory(question="Что есть?")]).is_empty()
    assert not OperationList(adds=[AddItem.model_validate(add())]).is_empty()
    assert OperationList().is_empty()


def test_json_schema_uses_flat_lists_and_float_quantities() -> None:
    schema = OperationList.model_json_schema()
    serialized = json.dumps(schema)
    assert "oneOf" not in serialized
    assert "discriminator" not in serialized
    assert set(schema["properties"]) == {
        "adds",
        "consumes",
        "discards",
        "updates",
        "queries",
        "undo_last",
    }
    assert all(
        schema["properties"][name]["type"] == "array"
        for name in ("adds", "consumes", "discards", "updates", "queries")
    )
    assert schema["properties"]["undo_last"]["type"] == "boolean"
    assert schema["$defs"]["AddItem"]["properties"]["quantity"]["type"] == "number"
