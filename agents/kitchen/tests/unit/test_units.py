from decimal import Decimal, localcontext

import pytest
from kitchen.domain.model import Unit
from kitchen.domain.units import InputUnit, humanize_quantity, normalize_quantity


@pytest.mark.parametrize(
    ("quantity", "unit", "expected"),
    [
        ("2", InputUnit.L, (Decimal("2000"), Unit.ML)),
        ("0.3", InputUnit.KG, (Decimal("300"), Unit.G)),
        ("10", InputUnit.PCS, (Decimal("10"), Unit.PCS)),
        ("1", "pack", (Decimal("1"), Unit.PACK)),
        ("250", InputUnit.G, (Decimal("250"), Unit.G)),
    ],
)
def test_normalize(quantity: str, unit: InputUnit | str, expected: tuple[Decimal, Unit]) -> None:
    assert normalize_quantity(Decimal(quantity), unit) == expected


def test_normalize_rejects_unknown_unit() -> None:
    with pytest.raises(ValueError, match="bucket"):
        normalize_quantity(Decimal(1), "bucket")


@pytest.mark.parametrize(
    ("quantity", "unit", "expected"),
    [
        ("2000", Unit.ML, (Decimal("2"), "l")),
        ("1500", Unit.ML, (Decimal("1.5"), "l")),
        ("500", Unit.ML, (Decimal("500"), "ml")),
        ("300.000", Unit.G, (Decimal("300"), "g")),
        ("1000", Unit.G, (Decimal("1"), "kg")),
        ("3", Unit.PCS, (Decimal("3"), "pcs")),
    ],
)
def test_humanize(quantity: str, unit: Unit, expected: tuple[Decimal, str]) -> None:
    value, key = humanize_quantity(Decimal(quantity), unit)
    assert (value, key) == expected
    assert "E" not in str(value)


@pytest.mark.parametrize(
    ("quantity", "unit", "expected"),
    [
        ("0.000001", InputUnit.KG, (Decimal("0.001"), Unit.G)),
        ("999.999", InputUnit.ML, (Decimal("999.999"), Unit.ML)),
        ("1.2345", InputUnit.G, (Decimal("1.234"), Unit.G)),
        ("1.2355", InputUnit.G, (Decimal("1.236"), Unit.G)),
    ],
)
def test_normalization_precision(
    quantity: str, unit: InputUnit, expected: tuple[Decimal, Unit]
) -> None:
    assert normalize_quantity(Decimal(quantity), unit) == expected


@pytest.mark.parametrize("quantity", ["0.001", "999.999", "1000000"])
def test_humanize_keeps_plain_decimal_notation(quantity: str) -> None:
    value, key = humanize_quantity(Decimal(quantity), Unit.PACK)
    assert value == Decimal(quantity)
    assert key == "pack"
    assert "E" not in str(value)


@pytest.mark.parametrize("quantity", ["0", "-1", "NaN", "Infinity", "-Infinity", "0.0004"])
def test_normalize_rejects_unusable_quantities(quantity: str) -> None:
    with pytest.raises(ValueError, match="Quantity"):
        normalize_quantity(Decimal(quantity), InputUnit.G)


def test_humanize_consumed_quantity_keeps_zero() -> None:
    assert humanize_quantity(Decimal("0.000"), Unit.ML) == (Decimal(0), "ml")


def test_humanize_preserves_long_fraction_coefficient() -> None:
    quantity = Decimal("0.12345678901234567890123456789")
    value, key = humanize_quantity(quantity, Unit.PACK)
    assert value == quantity
    assert key == "pack"


@pytest.mark.parametrize("unit", [Unit.G, Unit.ML])
def test_humanize_conversion_preserves_long_coefficient(unit: Unit) -> None:
    quantity = Decimal("1234.567890123456789012345678901")
    value, key = humanize_quantity(quantity, unit)
    assert value == Decimal("1.234567890123456789012345678901")
    assert key == ("kg" if unit is Unit.G else "l")


@pytest.mark.parametrize(
    ("quantity", "unit", "expected"),
    [
        ("12345.678", Unit.PACK, (Decimal("12345.678"), "pack")),
        ("12345.678", Unit.G, (Decimal("12.345678"), "kg")),
        ("12345.678", Unit.ML, (Decimal("12.345678"), "l")),
        ("1000000", Unit.PCS, (Decimal("1000000"), "pcs")),
    ],
)
def test_humanize_preserves_stored_quantity_with_low_ambient_precision(
    quantity: str, unit: Unit, expected: tuple[Decimal, str]
) -> None:
    with localcontext() as context:
        context.prec = 4
        assert humanize_quantity(Decimal(quantity), unit) == expected
        assert context.prec == 4


@pytest.mark.parametrize(
    ("quantity", "unit", "expected"),
    [
        ("12345.678", InputUnit.G, (Decimal("12345.678"), Unit.G)),
        ("12.345678", InputUnit.KG, (Decimal("12345.678"), Unit.G)),
        ("12.345678", InputUnit.L, (Decimal("12345.678"), Unit.ML)),
        ("1E+30", InputUnit.PCS, (Decimal("1000000000000000000000000000000.000"), Unit.PCS)),
    ],
)
def test_normalize_keeps_storage_precision_with_low_ambient_precision(
    quantity: str, unit: InputUnit, expected: tuple[Decimal, Unit]
) -> None:
    with localcontext() as context:
        context.prec = 4
        assert normalize_quantity(Decimal(quantity), unit) == expected
        assert context.prec == 4


def test_normalize_rounds_once_at_storage_precision() -> None:
    quantity = Decimal("1.234500000000000000000000000001")
    assert normalize_quantity(quantity, InputUnit.G) == (Decimal("1.235"), Unit.G)
