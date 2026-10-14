"""Matching helpers for kitchen extraction golden cases."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from kitchen.application.schema import OperationList
from kitchen.domain.rules import normalize_name
from kitchen.domain.units import normalize_quantity
from rapidfuzz import fuzz

KINDS = ("adds", "consumes", "discards", "updates")
NAME_FIELD = {"adds": "name", "consumes": "item_ref", "discards": "item_ref", "updates": "item_ref"}


def same_name(expected: str, actual: str) -> bool:
    return fuzz.WRatio(normalize_name(expected), normalize_name(actual)) >= 85


def same_quantity(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    if "quantity" not in expected:
        return True
    if actual.get("quantity") is None:
        return False
    exp_unit = expected.get("unit") or actual.get("unit") or "pcs"
    act_unit = actual.get("unit") or exp_unit
    try:
        want = normalize_quantity(Decimal(str(expected["quantity"])), exp_unit)
        got = normalize_quantity(Decimal(str(actual["quantity"])), act_unit)
    except ValueError:
        # Schema-valid positive amounts can fall below domain storage precision.
        return False
    return want == got


def matches(kind: str, expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    field = NAME_FIELD[kind]
    if not same_name(str(expected[field]), str(actual.get(field, ""))):
        return False
    if not same_quantity(expected, actual):
        return False
    return all(
        key not in expected or str(actual.get(key)).lower() == str(expected[key]).lower()
        for key in ("location", "opened", "expires_on")
    )


def _match_all(kind: str, wanted: list[dict[str, Any]], got: list[dict[str, Any]]) -> bool:
    # An augmenting path gives every expectation a distinct item, even when a
    # broad expectation initially takes the only match for a specific one.
    assigned: dict[int, int] = {}

    def assign(wanted_index: int, visited: set[int]) -> bool:
        for actual_index, item in enumerate(got):
            if actual_index in visited or not matches(kind, wanted[wanted_index], item):
                continue
            visited.add(actual_index)
            if actual_index not in assigned or assign(assigned[actual_index], visited):
                assigned[actual_index] = wanted_index
                return True
        return False

    return all(assign(index, set()) for index in range(len(wanted)))


def check(case: dict[str, Any], ops: OperationList | None) -> list[str]:
    if ops is None:
        return ["extraction failed (invalid output twice)"]
    actual = ops.model_dump(mode="json")
    expect = case.get("expect") or {}
    problems = []
    for kind in KINDS:
        wanted = list(expect.get(kind, []))
        got = list(actual[kind])
        if len(wanted) != len(got):
            problems.append(f"{kind}: expected {len(wanted)}, got {len(got)}: {got}")
        elif not _match_all(kind, wanted, got):
            problems.append(f"{kind}: no distinct matches for {wanted} in {got}")
    if len(actual["queries"]) != int(expect.get("queries", 0)):
        problems.append(
            f"queries: expected {expect.get('queries', 0)}, got {len(actual['queries'])}"
        )
    wanted_undo = bool(expect.get("undo_last", False))
    if actual["undo_last"] is not wanted_undo:
        problems.append(f"undo_last: expected {wanted_undo}, got {actual['undo_last']}")
    return problems


def inventory_text(names: list[str]) -> str:
    return "\n".join(
        f"- {name} | {name} | 1 pcs | fridge | opened=no | expires 2026-10-20" for name in names
    )
