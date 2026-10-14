"""Units: what people say (kg, l) vs. what we store (g, ml)."""

from __future__ import annotations

from decimal import Decimal, getcontext, localcontext
from enum import StrEnum

from kitchen.domain.model import Unit


class InputUnit(StrEnum):
    PCS = "pcs"
    G = "g"
    KG = "kg"
    ML = "ml"
    L = "l"
    PACK = "pack"


_FACTORS: dict[InputUnit, tuple[int, Unit]] = {
    InputUnit.PCS: (1, Unit.PCS),
    InputUnit.G: (1, Unit.G),
    InputUnit.KG: (1000, Unit.G),
    InputUnit.ML: (1, Unit.ML),
    InputUnit.L: (1000, Unit.ML),
    InputUnit.PACK: (1, Unit.PACK),
}
_THOUSANDTH = Decimal("0.001")


def normalize_quantity(quantity: Decimal, unit: InputUnit | str) -> tuple[Decimal, Unit]:
    factor, base = _FACTORS[InputUnit(unit)]
    if not quantity.is_finite() or quantity <= 0:
        raise ValueError("Quantity must be finite and positive")
    with localcontext() as context:
        context.prec = _working_precision(quantity)
        amount = (quantity * factor).quantize(_THOUSANDTH)
    if amount <= 0:
        raise ValueError("Quantity is below the supported precision")
    return amount, base


def humanize_quantity(quantity: Decimal, unit: Unit) -> tuple[Decimal, str]:
    with localcontext() as context:
        context.prec = _working_precision(quantity)
        if unit is Unit.G and quantity >= 1000:
            return _trim(quantity / 1000), "kg"
        if unit is Unit.ML and quantity >= 1000:
            return _trim(quantity / 1000), "l"
        return _trim(quantity), unit.value


def _working_precision(quantity: Decimal) -> int:
    # Retain the coefficient through scaling and allow integer digits plus 0.001 precision.
    return max(getcontext().prec, len(quantity.as_tuple().digits) + 3, quantity.adjusted() + 7)


def _trim(value: Decimal) -> Decimal:
    normalized = value.normalize()
    if normalized == normalized.to_integral_value():
        return normalized.quantize(Decimal(1))
    return normalized
