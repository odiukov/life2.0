from uuid import UUID

from kitchen.adapters.matching import RapidfuzzMatcher
from kitchen.application.resolve import (
    Ambiguous,
    NotFound,
    Resolved,
    build_resolution_context,
    resolve_ref,
)
from kitchen.application.schema import (
    AddItem,
    ConsumeItem,
    OperationList,
    UpdateItem,
)
from kitchen.domain.model import Status, Unit
from kitchen.testing import make_batch

MATCHER = RapidfuzzMatcher()


def test_exact_name_resolves() -> None:
    assert resolve_ref("Сыр", ["сыр", "сырки"], MATCHER) == Resolved("сыр")


def test_single_close_name_resolves() -> None:
    assert resolve_ref("молочко", ["молоко", "хлеб"], MATCHER) == Resolved("молоко")


def test_similar_names_are_ambiguous() -> None:
    result = resolve_ref("сыр", ["сыр российский", "сыр моцарелла", "хлеб"], MATCHER)
    assert isinstance(result, Ambiguous)
    assert set(result.candidates) == {"сыр российский", "сыр моцарелла"}


def test_nothing_similar_is_not_found() -> None:
    assert resolve_ref("ананас", ["молоко", "хлеб"], MATCHER) == NotFound("ананас")
    assert resolve_ref("ананас", [], MATCHER) == NotFound("ананас")


def test_names_are_normalized_and_deduplicated() -> None:
    assert resolve_ref("  МОЛОКО  ", ["Молоко", "молоко"], MATCHER) == Resolved("молоко")
    assert resolve_ref("пюре", ["ПЮРЁ"], MATCHER) == Resolved("пюре")


def test_context_includes_new_names_for_later_operations() -> None:
    operations = OperationList(
        adds=[
            AddItem(
                name="  СЫР  ",
                display_name="сыр",
                quantity=1,
                unit="kg",
                location="fridge",
                category="dairy",
                shelf_life_days=7,
            )
        ],
        consumes=[ConsumeItem(item_ref="сыр", quantity=50, unit="g")],
        updates=[UpdateItem(item_ref="сыр", opened=True)],
    )
    context = build_resolution_context([], operations.adds)
    for ref in operations.item_refs():
        assert resolve_ref(ref, context.names, MATCHER) == Resolved("сыр")
    candidates = context.for_name("Сыр")
    assert len(candidates) == 1
    assert candidates[0].name == "сыр"
    assert candidates[0].unit is Unit.G
    assert candidates[0].batch_id is None


def test_context_preserves_ids_and_incompatible_units_for_clarification() -> None:
    context = build_resolution_context(
        [
            make_batch(id=1, name="молоко", unit=Unit.ML),
            make_batch(id=2, name="молоко", unit=Unit.PACK),
            make_batch(id=3, name="хлеб", status=Status.CONSUMED),
        ],
        [],
    )
    assert context.names == ["молоко"]
    assert resolve_ref("молоко", context.names, MATCHER) == Resolved("молоко")
    assert {(c.batch_id, c.unit) for c in context.for_name("молоко")} == {
        (UUID(int=1), Unit.ML),
        (UUID(int=2), Unit.PACK),
    }
    assert context.for_name("хлеб") == ()
