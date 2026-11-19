from decimal import Decimal

_MASS_FACTORS: dict[str, Decimal] = {
    "kg": Decimal(1),
    "g": Decimal("0.001"),
    "t": Decimal(1000),
}

_COUNT_ALIASES = {"un": "un", "unidade": "un", "unidades": "un"}


class IncompatibleUnitError(ValueError):
    pass


def normalize_unit(unit: str | None) -> str | None:
    if unit is None:
        return None

    normalized = unit.strip().lower()
    if not normalized:
        return None

    return _COUNT_ALIASES.get(normalized, normalized)


def are_compatible(from_unit: str | None, to_unit: str | None) -> bool:
    source = normalize_unit(from_unit)
    target = normalize_unit(to_unit)

    if source is None or target is None:
        return False

    if source == target:
        return True

    return source in _MASS_FACTORS and target in _MASS_FACTORS


def convert_quantity(
    value: Decimal,
    from_unit: str | None,
    to_unit: str | None,
) -> Decimal:
    source = normalize_unit(from_unit)
    target = normalize_unit(to_unit)

    if source is None or target is None:
        raise IncompatibleUnitError(
            "A unidade do lote e a unidade do item devem estar preenchidas "
            "para converter a quantidade."
        )

    if source == target:
        return value

    if source in _MASS_FACTORS and target in _MASS_FACTORS:
        return value * _MASS_FACTORS[source] / _MASS_FACTORS[target]

    raise IncompatibleUnitError(
        f"Não há equivalência conhecida entre as unidades "
        f"'{from_unit}' e '{to_unit}'."
    )


def sum_quantities_in_unit(
    quantities: list[tuple[Decimal, str | None]],
    unit: str | None,
) -> Decimal | None:
    """Soma as quantidades convertidas para `unit`.

    Retorna `None` quando alguma unidade é incompatível ou ausente,
    sinalizando que o saldo é indeterminado.
    """
    target = normalize_unit(unit)
    if target is None:
        return None

    total = Decimal(0)
    for value, source_unit in quantities:
        source = normalize_unit(source_unit)
        if source is None:
            return None
        if source == target:
            total += value
            continue
        if source in _MASS_FACTORS and target in _MASS_FACTORS:
            total += value * _MASS_FACTORS[source] / _MASS_FACTORS[target]
            continue
        return None

    return total
