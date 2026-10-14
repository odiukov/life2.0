"""Offline checks for the kitchen extraction evaluation matcher."""

from pathlib import Path

import pytest
import yaml
from evals import matching
from kitchen.application.schema import OperationList


def test_duplicate_expectations_cannot_reuse_one_actual_item() -> None:
    case = {"expect": {"consumes": [{"item_ref": "milk"}, {"item_ref": "milk"}]}}
    actual = OperationList.model_validate(
        {"consumes": [{"item_ref": "milk"}, {"item_ref": "eggs"}]}
    )
    assert matching.check(case, actual)


def test_overlapping_expectations_match_regardless_of_order() -> None:
    case = {"expect": {"consumes": [{"item_ref": "milk"}, {"item_ref": "milk", "quantity": 1}]}}
    actual = OperationList.model_validate(
        {"consumes": [{"item_ref": "milk", "quantity": 1}, {"item_ref": "milk", "quantity": 2}]}
    )
    assert matching.check(case, actual) == []


@pytest.mark.parametrize(
    ("expected", "actual", "passes"),
    [
        ({"quantity": 0.5, "unit": "kg"}, {"quantity": 500, "unit": "g"}, True),
        ({"quantity": 2, "unit": "l"}, {"quantity": 2000, "unit": "ml"}, True),
        ({"quantity": 2, "unit": "pack"}, {"quantity": 2, "unit": "pcs"}, False),
        ({"quantity": 2, "unit": "l"}, {"quantity": 2, "unit": "ml"}, False),
        ({"quantity": 2}, {"quantity": None}, False),
    ],
)
def test_quantity_comparison_uses_normalized_amount_and_dimension(
    expected: dict[str, object], actual: dict[str, object], passes: bool
) -> None:
    assert matching.same_quantity(expected, actual) is passes


@pytest.mark.parametrize("kind", ["adds", "consumes", "discards", "updates", "queries"])
def test_chatter_rejects_every_unexpected_operation_kind(kind: str) -> None:
    operations = {
        "adds": [
            {
                "name": "milk",
                "display_name": "milk",
                "quantity": 1,
                "unit": "l",
                "location": "fridge",
                "category": "dairy",
                "shelf_life_days": 5,
            }
        ],
        "consumes": [{"item_ref": "milk"}],
        "discards": [{"item_ref": "milk"}],
        "updates": [{"item_ref": "milk", "opened": True}],
        "queries": [{"question": "What is left?"}],
    }
    assert matching.check({"expect": {}}, OperationList.model_validate({kind: operations[kind]}))


def test_queries_require_exact_count() -> None:
    actual = OperationList.model_validate({"queries": [{"question": "What is left?"}]})
    assert matching.check({"expect": {"queries": 1}}, actual) == []
    assert matching.check({"expect": {"queries": 2}}, actual) == ["queries: expected 2, got 1"]


@pytest.mark.parametrize(
    "actual", [{"opened": False}, {"location": "pantry"}, {"expires_on": "2026-10-21"}]
)
def test_update_attributes_are_checked(actual: dict[str, object]) -> None:
    expected = {
        "item_ref": "milk",
        "opened": True,
        "location": "fridge",
        "expires_on": "2026-10-20",
    }
    assert not matching.matches("updates", expected, {**expected, **actual})


def test_invalid_extraction_is_a_failed_case() -> None:
    assert matching.check({"expect": {}}, None) == ["extraction failed (invalid output twice)"]


def test_name_comparison_normalizes_case_and_diacritics() -> None:
    assert matching.same_name("Тушёнка", "тушенка")
    assert not matching.same_name("milk", "bread")


@pytest.mark.parametrize("kind", ["adds", "consumes"])
def test_schema_valid_subprecision_quantity_is_a_nonmatch(kind: str) -> None:
    actual_item: dict[str, object] = {"quantity": 0.0001, "unit": "ml"}
    expected_item: dict[str, object] = {"quantity": 1, "unit": "ml"}
    if kind == "adds":
        actual_item.update(
            name="milk",
            display_name="milk",
            location="fridge",
            category="dairy",
            shelf_life_days=5,
        )
        expected_item["name"] = "milk"
    else:
        actual_item["item_ref"] = "milk"
        expected_item["item_ref"] = "milk"
    actual = OperationList.model_validate({kind: [actual_item]})
    assert matching.check({"expect": {kind: [expected_item]}}, actual)


def test_undo_requires_explicit_expectation() -> None:
    actual = OperationList.model_validate({"undo_last": True})
    assert matching.check({"expect": {}}, actual) == ["undo_last: expected False, got True"]
    assert matching.check({"expect": {"undo_last": True}}, actual) == []


def test_golden_set_has_32_unique_nonempty_cases() -> None:
    path = Path(__file__).parent.parent / "evals" / "cases.yaml"
    cases = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert len(cases) == 32
    assert len({case["id"] for case in cases}) == 32
    assert all(case["text"] for case in cases)
    assert {cases[-2]["id"], cases[-1]["id"]} == {"undo_last", "clarification_answer"}
