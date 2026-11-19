from decimal import Decimal

import pytest

from api.helpers.units import (
    IncompatibleUnitError,
    are_compatible,
    convert_quantity,
    normalize_unit,
    sum_quantities_in_unit,
)


def test_normalize_unit_lowercases_and_trims() -> None:
    assert normalize_unit("  KG ") == "kg"
    assert normalize_unit("Unidade") == "un"
    assert normalize_unit("UNIDADES") == "un"
    assert normalize_unit(None) is None
    assert normalize_unit("   ") is None


def test_convert_same_unit_is_identity() -> None:
    assert convert_quantity(Decimal(10), "kg", "kg") == Decimal(10)


def test_convert_mass_units() -> None:
    assert convert_quantity(Decimal(1), "kg", "g") == Decimal(1000)
    assert convert_quantity(Decimal(1500), "g", "kg") == Decimal("1.500")
    assert convert_quantity(Decimal(1), "t", "kg") == Decimal(1000)


def test_convert_count_alias_is_identity() -> None:
    assert convert_quantity(Decimal(5), "un", "unidade") == Decimal(5)


def test_convert_preserves_precision_beyond_three_decimals() -> None:
    assert convert_quantity(Decimal("999.4"), "g", "kg") == Decimal("0.9994")
    assert convert_quantity(Decimal("0.0006"), "kg", "g") == Decimal("0.6")


def test_convert_incompatible_units_raises() -> None:
    with pytest.raises(IncompatibleUnitError):
        convert_quantity(Decimal(10), "kg", "caixa")


def test_convert_missing_unit_raises() -> None:
    with pytest.raises(IncompatibleUnitError):
        convert_quantity(Decimal(10), None, "kg")


def test_are_compatible() -> None:
    assert are_compatible("kg", "g") is True
    assert are_compatible("un", "unidade") is True
    assert are_compatible("kg", "caixa") is False
    assert are_compatible(None, "kg") is False


def test_sum_quantities_in_unit() -> None:
    total = sum_quantities_in_unit(
        [
            (Decimal(10), "kg"),
            (Decimal(500), "g"),
        ],
        "kg",
    )
    assert total == Decimal("10.500")


def test_sum_quantities_returns_none_on_incompatible() -> None:
    total = sum_quantities_in_unit(
        [(Decimal(10), "kg"), (Decimal(2), "caixa")],
        "kg",
    )
    assert total is None


def test_sum_quantities_returns_none_on_blank_unit() -> None:
    total = sum_quantities_in_unit([(Decimal(10), "kg")], None)
    assert total is None


def test_sum_quantities_preserves_conversion_precision() -> None:
    total = sum_quantities_in_unit([(Decimal("999.4"), "g")], "kg")
    assert total == Decimal("0.9994")
