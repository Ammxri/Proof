"""Numbers in an alternative unit (MR6, A-05, A-39): exact conversion, rounding and the way back.

The catalog states each alternative unit as ``shown = canonical * factor + offset`` with a number of decimals
(:class:`proof_rules.model.AltUnit`). Factor and offset are read as the decimal numbers they are written as, the
conversion is exact, and the shown number is rounded half away from zero. :func:`back` gives the canonical value a
shown number stands for; A-39 checks the rules with it.
"""

from __future__ import annotations

import math
from decimal import Decimal
from fractions import Fraction

from proof_rules.model import AltUnit, FieldDef


class UnitError(ValueError):
    """A field has no such alternative unit."""


def exact(value: int | float | Decimal) -> Fraction:
    """The decimal number a value is written as, as an exact fraction (``0.1`` is one tenth)."""
    return Fraction(str(value))


def round_half_away(value: Fraction, decimals: int) -> Decimal:
    """``value`` rounded to ``decimals`` places, ties away from zero, as a decimal with exactly that many places."""
    units = math.floor(abs(value) * 10**decimals + Fraction(1, 2))
    signed = -units if value < 0 and units else units
    return Decimal(signed).scaleb(-decimals)


def shown(value: int | float, alt: AltUnit) -> Decimal:
    """The number shown for a canonical ``value`` in ``alt``."""
    return round_half_away(exact(value) * exact(alt.factor) + exact(alt.offset), alt.decimals)


def back(number: Decimal, alt: AltUnit) -> Fraction:
    """The canonical value a number shown in ``alt`` stands for, exactly."""
    return (exact(number) - exact(alt.offset)) / exact(alt.factor)


def alt_unit(field: FieldDef, unit: str) -> AltUnit:
    """The alternative unit ``unit`` of ``field``."""
    for alt in field.alt_units:
        if alt.unit == unit:
            return alt
    available = ", ".join(alt.unit for alt in field.alt_units) or "none"
    raise UnitError(f"{field.code} has no alternative unit {unit!r} (available: {available})")
