"""Constraints on fact values, derived from rule conditions, for the case sampler (A-66).

The sampler reaches its target through the rules themselves. A condition that must be true (or false) is expanded into
the alternative ways it can be met, its disjunctive normal form. Each alternative, a *term*, restricts a few fields to
allowed values and leaves every other field free. A base case is complete, so the logic is two-valued there, and facts
that satisfy a term make the condition true (or false) whatever values the free fields take.

Numeric values live on the grid of their field: ``units = value * 10**decimals`` is an integer. Allowed numeric values
are sets of integer intervals over these units; allowed values of bool and enum fields are finite sets. Every literal
is derived from :func:`proof_rules.logic.compare_values`, the comparison the engine uses, so sampler and engine agree,
also at thresholds that fall between two grid points.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
from typing import Any

from proof_rules.logic import compare_values, threshold
from proof_rules.model import AllOf, AnyOf, AtLeast, Compare, Condition, FieldDef, Not, RefRange

MAX_TERMS = 4096

Bound = int | None


class ConstraintError(ValueError):
    """A condition cannot be turned into constraints (unknown field, too many alternatives, broken grid)."""


# --- Grid ------------------------------------------------------------------------------------------------------------


def scale(field: FieldDef) -> int:
    """Grid steps per unit of a numeric field: ``10**decimals``; int fields and fields without decimals have 1."""
    return 10 ** (field.decimals or 0)


def value_of(field: FieldDef, units: int) -> int | float:
    """The fact value at ``units`` grid steps; an ``int`` when the field has no decimals, as facts are stored."""
    if field.type == "int" or not field.decimals:
        return units
    return units / scale(field)


def units_of(field: FieldDef, value: int | float) -> int:
    """Grid steps of a value that lies on the field's grid; the decimal form of the value is used exactly."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConstraintError(f"{field.code}: {value!r} is not a number")
    exact = Fraction(str(value)) * scale(field)
    if exact.denominator != 1:
        raise ConstraintError(f"{field.code}: {value} is not on the grid of {field.decimals or 0} decimals")
    return exact.numerator


# --- Integer interval sets -------------------------------------------------------------------------------------------


def _lower_key(bound: Bound) -> tuple[int, int]:
    return (0, 0) if bound is None else (1, bound)


@dataclass(frozen=True)
class Intervals:
    """A set of integers: sorted, disjoint, non-adjacent closed intervals; ``None`` is an open end."""

    parts: tuple[tuple[Bound, Bound], ...]

    @classmethod
    def of(cls, parts: Iterable[tuple[Bound, Bound]]) -> Intervals:
        items = sorted((part for part in parts if _valid(part)), key=lambda part: _lower_key(part[0]))
        merged: list[tuple[Bound, Bound]] = []
        for lower, upper in items:
            if merged:
                last_lower, last_upper = merged[-1]
                if last_upper is None or lower is None or lower <= last_upper + 1:
                    joined = None if last_upper is None or upper is None else max(last_upper, upper)
                    merged[-1] = (last_lower, joined)
                    continue
            merged.append((lower, upper))
        return cls(tuple(merged))

    @classmethod
    def everything(cls) -> Intervals:
        return cls(((None, None),))

    @classmethod
    def nothing(cls) -> Intervals:
        return cls(())

    @classmethod
    def point(cls, value: int) -> Intervals:
        return cls(((value, value),))

    def is_empty(self) -> bool:
        return not self.parts

    def union(self, other: Intervals) -> Intervals:
        return Intervals.of((*self.parts, *other.parts))

    def intersect(self, other: Intervals) -> Intervals:
        result = []
        for lower_a, upper_a in self.parts:
            for lower_b, upper_b in other.parts:
                lower = lower_b if lower_a is None else lower_a if lower_b is None else max(lower_a, lower_b)
                upper = upper_b if upper_a is None else upper_a if upper_b is None else min(upper_a, upper_b)
                result.append((lower, upper))
        return Intervals.of(result)

    def complement(self) -> Intervals:
        result: list[tuple[Bound, Bound]] = []
        start: Bound = None
        open_start = True
        for lower, upper in self.parts:
            if lower is not None and (open_start or (start is not None and start <= lower - 1)):
                result.append((None if open_start else start, lower - 1))
            if upper is None:
                return Intervals(tuple(result))
            start, open_start = upper + 1, False
        result.append((None if open_start else start, None))
        return Intervals(tuple(result))

    def _clipped(self, low: int, high: int) -> Iterable[tuple[int, int]]:
        for lower, upper in self.parts:
            first = low if lower is None else max(low, lower)
            last = high if upper is None else min(high, upper)
            if first <= last:
                yield first, last

    def count_in(self, low: int, high: int) -> int:
        """How many members lie in ``[low, high]``."""
        return sum(last - first + 1 for first, last in self._clipped(low, high))

    def nth_in(self, low: int, high: int, index: int) -> int:
        """The member at position ``index`` (from 0, ascending) among the members in ``[low, high]``."""
        for first, last in self._clipped(low, high):
            size = last - first + 1
            if index < size:
                return first + index
            index -= size
        raise IndexError("index outside the members in the range")


def _valid(part: tuple[Bound, Bound]) -> bool:
    lower, upper = part
    return lower is None or upper is None or lower <= upper


# --- Allowed values and terms ----------------------------------------------------------------------------------------

Allowed = Intervals | frozenset


def is_empty(allowed: Allowed) -> bool:
    return allowed.is_empty() if isinstance(allowed, Intervals) else not allowed


def intersect(first: Allowed, second: Allowed) -> Allowed:
    if isinstance(first, Intervals) and isinstance(second, Intervals):
        return first.intersect(second)
    if isinstance(first, frozenset) and isinstance(second, frozenset):
        return first & second
    raise ConstraintError("cannot combine numeric and discrete constraints")  # pragma: no cover - fields have one type


def _value_key(value: Any) -> tuple[str, str]:
    return (type(value).__name__, repr(value))


@dataclass(frozen=True)
class Term:
    """A conjunction of constraints: field code → allowed values, sorted by field code. Fields not listed are free."""

    constraints: tuple[tuple[str, Allowed], ...] = ()

    def get(self, code: str) -> Allowed | None:
        for field, allowed in self.constraints:
            if field == code:
                return allowed
        return None

    def fields(self) -> tuple[str, ...]:
        return tuple(field for field, _ in self.constraints)

    def conjoin(self, other: Term) -> Term | None:
        """Both terms at once, or ``None`` if some field would have no allowed value left."""
        merged = dict(self.constraints)
        for field, allowed in other.constraints:
            combined = allowed if field not in merged else intersect(merged[field], allowed)
            if is_empty(combined):
                return None
            merged[field] = combined
        return Term(tuple(sorted(merged.items())))


EMPTY_TERM = Term()


def describe(allowed: Allowed) -> str:
    """Short text form for messages, e.g. ``{True}`` or ``[381, ∞]`` in grid steps."""
    if isinstance(allowed, frozenset):
        return "{" + ", ".join(repr(value) for value in sorted(allowed, key=_value_key)) + "}"
    parts = []
    for lower, upper in allowed.parts:
        parts.append(f"[{'-∞' if lower is None else lower}, {'∞' if upper is None else upper}]")
    return " or ".join(parts) or "empty"


def _cap(terms: Sequence[Term]) -> list[Term]:
    unique = list(dict.fromkeys(terms))
    if len(unique) > MAX_TERMS:
        raise ConstraintError(f"a condition has more than {MAX_TERMS} alternatives; the sampler cannot expand it")
    return unique


def product(first: Sequence[Term], second: Sequence[Term]) -> list[Term]:
    """Every consistent conjunction of one term of ``first`` and one of ``second``."""
    result = []
    for left in first:
        for right in second:
            combined = left.conjoin(right)
            if combined is not None:
                result.append(combined)
    return _cap(result)


# --- Expansion -------------------------------------------------------------------------------------------------------

Support = Callable[[str, Allowed], bool]


class Expander:
    """Expands conditions of one domain into terms. ``support`` rejects allowed sets the sampler cannot draw from."""

    def __init__(
        self,
        fields: Mapping[str, FieldDef],
        references: Mapping[str, RefRange],
        support: Support | None = None,
    ) -> None:
        self._fields = fields
        self._references = references
        self._support = support

    def field(self, code: str) -> FieldDef:
        definition = self._fields.get(code)
        if definition is None:
            raise ConstraintError(f"{code}: not a field of the domain")
        return definition

    def domain_of(self, code: str) -> Allowed:
        """All values a field can take, before any condition."""
        definition = self.field(code)
        if definition.type == "bool":
            return frozenset((False, True))
        if definition.type == "enum":
            return frozenset(definition.values)
        return Intervals.everything()

    def literal(self, compare: Compare) -> Allowed:
        """The values of the compared field for which the comparison is true."""
        definition = self.field(compare.field)
        expected = threshold(compare, self._references)
        if definition.type in ("bool", "enum"):
            values = (False, True) if definition.type == "bool" else definition.values
            return frozenset(value for value in values if compare_values(compare.op, value, expected))
        return _numeric_literal(definition, compare.op, expected)

    def expand(self, condition: Condition, want: bool) -> list[Term]:
        """The terms under which ``condition`` evaluates to ``want`` on complete facts."""
        if isinstance(condition, Compare):
            allowed = self.literal(condition)
            if not want:
                allowed = _complement(allowed, self.domain_of(condition.field))
            if is_empty(allowed) or (self._support is not None and not self._support(condition.field, allowed)):
                return []
            return [Term(((condition.field, allowed),))]
        if isinstance(condition, Not):
            return self.expand(condition.negated, not want)
        if isinstance(condition, AllOf):
            return self._all(condition.all, True) if want else self._any(condition.all, False)
        if isinstance(condition, AnyOf):
            return self._any(condition.any, True) if want else self._all(condition.any, False)
        if isinstance(condition, AtLeast):
            parts = condition.of
            need = condition.at_least if want else len(parts) - condition.at_least + 1
            result: list[Term] = []
            for chosen in combinations(parts, need):
                result.extend(self._all(chosen, want))
            return _cap(result)
        raise ConstraintError(f"not a condition: {type(condition).__name__}")  # pragma: no cover - model forbids it

    def _all(self, parts: Sequence[Condition], want: bool) -> list[Term]:
        terms = [EMPTY_TERM]
        for part in parts:
            terms = product(terms, self.expand(part, want))
            if not terms:
                return []
        return terms

    def _any(self, parts: Sequence[Condition], want: bool) -> list[Term]:
        result: list[Term] = []
        for part in parts:
            result.extend(self.expand(part, want))
        return _cap(result)


def _complement(allowed: Allowed, domain: Allowed) -> Allowed:
    if isinstance(allowed, Intervals):
        return allowed.complement()
    return frozenset(domain) - allowed


def _grid_point(field: FieldDef, value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    exact = Fraction(str(value)) * scale(field)
    return exact.numerator if exact.denominator == 1 else None


def _numeric_literal(field: FieldDef, op: str, expected: Any) -> Intervals:
    if op in ("eq", "ne", "in"):
        items = expected if op == "in" else (expected,)
        points = Intervals.nothing()
        for item in items:
            units = _grid_point(field, item)
            if units is not None and compare_values("eq", value_of(field, units), item):
                points = points.union(Intervals.point(units))
        return points.complement() if op == "ne" else points
    centre = math.floor(Fraction(str(expected)) * scale(field))
    window = range(centre - 2, centre + 3)
    holds = [compare_values(op, value_of(field, units), expected) for units in window]
    upward = op in ("gt", "ge")
    expected_shape = sorted(holds) if upward else sorted(holds, reverse=True)
    if holds != expected_shape or all(holds) or not any(holds):
        raise ConstraintError(f"{field.code}: cannot place threshold {expected} on the grid")  # pragma: no cover
    if upward:
        return Intervals(((window[holds.index(True)], None),))
    return Intervals(((None, window[len(holds) - 1 - holds[::-1].index(True)]),))
